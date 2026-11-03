"""Application generation and idempotent application of verified setup results."""
import os
from pathlib import Path
import tempfile
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from datetime import datetime

from .exchange import canonical_json
from .setup_validation import validate_result
from ..models.project import Project, ProjectManager, ProjectStatus
from ..services.ontology_generator import OntologyGenerator
from ..services.oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
from ..services.simulation_config_generator import SimulationConfigGenerator
from ..services.simulation_manager import SimulationManager
from ..services.zep_entity_reader import EntityNode
from ..utils.locale import set_locale


class ValidatedClient:
    def __init__(self, client):
        self.client, self.model = client, client.model

    def chat_json(self, messages, **kwargs):
        result = self.client.chat_json(messages, **kwargs)
        # Consumers normalize their input; retain the exact verified receipt.
        return deepcopy(validate_result(kwargs.get('purpose', 'ontology'), result))


def atomic_json(path, value):
    atomic_text(path, canonical_json(value) + '\n')


def atomic_text(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode='w', encoding='utf-8', delete=False) as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = stream.name
    try:
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def materialize_project(inputs):
    """Recover interrupted local writes from the immutable workflow input."""
    project = ProjectManager.get_project(inputs['project_id'])
    if project is None:
        timestamp = datetime.now().isoformat()
        project = Project(inputs['project_id'],inputs['project_name'],ProjectStatus.CREATED,timestamp,timestamp,
                          files=inputs['files'],simulation_requirement=inputs['simulation_requirement'],
                          total_text_length=sum(map(len,inputs['document_texts'])))
        Path(ProjectManager._get_project_dir(project.project_id)).mkdir(parents=True,exist_ok=True)
        atomic_json(ProjectManager._get_project_meta_path(project.project_id),project.to_dict())
    if project.simulation_requirement and project.simulation_requirement != inputs['simulation_requirement']:
        raise ValueError('Project requirement changed')
    expected = '\n\n'.join(inputs['document_texts'])
    actual = ProjectManager.get_extracted_text(project.project_id)
    if actual is None:
        atomic_text(ProjectManager._get_project_text_path(project.project_id), expected)
    elif actual != expected:
        raise ValueError('Project source text changed; existing text preserved')
    return project


class SetupEngine:
    def generate(self, kind, inputs, client):
        set_locale(inputs.get('locale', 'en'))
        client = ValidatedClient(client)
        if kind == 'ontology':
            return OntologyGenerator(client).generate(inputs['document_texts'],
                inputs['simulation_requirement'], inputs.get('additional_context'))
        if kind == 'simulation':
            entities = [EntityNode(**value) for value in inputs['entities']]
            state = inputs['state']
            generator = OasisProfileGenerator(llm_client=client, entity_contexts=inputs['entity_contexts'])
            profiles = []
            for index, entity in enumerate(entities):
                profile = generator.generate_profile_from_entity(entity, index)
                # Stable identity and timestamps are necessary for restart replay.
                profile.user_name = 'agent_' + sha256(entity.uuid.encode()).hexdigest()[:16]
                profile.created_at = state['created_at'][:10]
                profiles.append(asdict(profile))
            config = SimulationConfigGenerator(llm_client=client).generate_config(
                state['simulation_id'], state['project_id'], state['graph_id'],
                inputs['simulation_requirement'], inputs['document_text'], entities,
                state['enable_twitter'], state['enable_reddit']).to_dict()
            config['generated_at'] = state['created_at']
            return {'profiles':profiles, 'config':config}
        raise ValueError('Unknown setup kind')

    def apply(self, workflow):
        if workflow['kind'] == 'ontology':
            project = materialize_project(workflow['inputs'])
            if project is None or workflow['inputs']['project_id'] != project.project_id:
                raise ValueError('Setup project disappeared or changed')
            result = workflow['result']
            ontology = {key:result[key] for key in ('entity_types','edge_types')}
            if project.ontology:
                if project.ontology != ontology or project.analysis_summary != result['analysis_summary']:
                    raise ValueError('Existing ontology changed')
                # A later graph step may already have advanced the project.
                return
            project.ontology, project.analysis_summary = ontology, result['analysis_summary']
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            atomic_json(ProjectManager._get_project_meta_path(project.project_id), project.to_dict())
            return
        if workflow['kind'] == 'simulation':
            self.apply_simulation(workflow)
            return
        raise ValueError('Unknown setup kind')

    def apply_simulation(self, workflow):
        manager = SimulationManager()
        state = manager.get_simulation(workflow['resource'])
        frozen = workflow['inputs']['state']
        if state is None or any(state.to_dict()[key] != frozen[key] for key in
                ('simulation_id','project_id','graph_id','enable_twitter','enable_reddit')):
            raise ValueError('Setup simulation disappeared or changed')
        result = workflow['result']
        directory = Path(manager._get_simulation_dir(state.simulation_id))
        profiles = [OasisAgentProfile(**value) for value in result['profiles']]
        # Existing format writers are used unchanged; only publish complete files.
        writer = OasisProfileGenerator(llm_client=type('NoGeneration', (), {'model':'gpt-6.1-sol'})(), entity_contexts={})
        with tempfile.TemporaryDirectory(dir=directory) as staging:
            stage = Path(staging)
            if state.enable_reddit: writer.save_profiles(profiles, str(stage / 'reddit_profiles.json'), 'reddit')
            if state.enable_twitter: writer.save_profiles(profiles, str(stage / 'twitter_profiles.csv'), 'twitter')
            atomic_json(stage / 'simulation_config.json', result['config'])
            for path in stage.iterdir():
                destination = directory / path.name
                if destination.exists() and destination.read_bytes() != path.read_bytes():
                    raise ValueError('Existing simulation output differs; preserved for inspection')
                os.replace(path, destination)
        ready = {**frozen, 'status':'ready', 'entities_count':len(profiles), 'profiles_count':len(profiles),
                 'entity_types':sorted({p.source_entity_type for p in profiles}),
                 'profiles_generated':True, 'config_generated':True,
                 'config_reasoning':result['config']['generation_reasoning'], 'error':None}
        atomic_json(directory / 'state.json', ready)
