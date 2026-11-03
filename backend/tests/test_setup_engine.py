from types import SimpleNamespace
from unittest.mock import Mock
from copy import deepcopy

import pytest

from app.agent_runners.setup_coordinator import GenerationPending, ReplayClient
from app.agent_runners.setup_engine import SetupEngine
from app.models.project import ProjectManager
from app.models.project import ProjectStatus
from test_setup_validation import RESULTS
from app.services.simulation_manager import SimulationManager
from app.services.zep_entity_reader import EntityNode


def simulation_inputs(state):
    entity = EntityNode('alice', 'Alice', ['Customer'], 'Budget conscious customer', {})
    return {'state':state.to_dict(), 'entities':[entity.to_dict()], 'entity_contexts':{'alice':'Frozen graph facts'},
            'simulation_requirement':'Explore price change', 'document_text':'A fictional price increase.'}


def test_ontology_replay_applies_to_normal_project_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    project = ProjectManager.create_project('Fictional pricing')
    inputs = {'project_id': project.project_id, 'document_texts':['A fictional price change.'],
              'simulation_requirement':'Explore customer reactions', 'additional_context':None}
    engine = SetupEngine()
    with pytest.raises(GenerationPending) as pending:
        engine.generate('ontology', inputs, ReplayClient([]))
    packet = pending.value.packet
    assert packet['kind'] == 'ontology'
    client = ReplayClient([{'packet':packet, 'status':'succeeded', 'response':{'result':RESULTS['ontology']}}])
    result = engine.generate('ontology', inputs, client)
    workflow = {'id':'a'*32, 'kind':'ontology', 'resource':project.project_id, 'inputs':inputs, 'result':result}
    engine.apply(workflow)
    saved = ProjectManager.get_project(project.project_id).to_dict()
    assert saved['status'] == 'ontology_generated'
    assert saved['analysis_summary'] == RESULTS['ontology']['analysis_summary']
    engine.apply(workflow)
    assert ProjectManager.get_project(project.project_id).to_dict() == saved
    progressed = ProjectManager.get_project(project.project_id)
    progressed.status, progressed.graph_id = ProjectStatus.GRAPH_COMPLETED, 'existing-graph'
    ProjectManager.save_project(progressed)
    engine.apply(workflow)
    assert ProjectManager.get_project(project.project_id).status == ProjectStatus.GRAPH_COMPLETED


def test_generation_consumers_do_not_mutate_verified_response_evidence():
    original = {'entity_types':[{'name':'Customer','description':'Customer','attributes':[]}],
                'edge_types':[], 'analysis_summary':'Fictional scenario'}
    evidence = deepcopy(original)
    client = SimpleNamespace(model='gpt-6.1-sol',chat_json=lambda *a,**kw:evidence)
    SetupEngine().generate('ontology',{'document_texts':['Fictional price change'],
                                      'simulation_requirement':'Explore reactions'},client)
    assert evidence == original


def test_simulation_uses_frozen_inputs_and_writes_normal_consumer_files(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path))
    manager = SimulationManager()
    state = manager.create_simulation('proj_abcdef', 'graph-fixture', True, True)
    inputs = simulation_inputs(state)
    calls = []
    client = SimpleNamespace(model='gpt-6.1-sol')
    def generate(messages, **kwargs):
        kind = kwargs.get('purpose')
        calls.append(kind)
        return RESULTS[kind]
    client.chat_json = generate
    engine = SetupEngine()
    result = engine.generate('simulation', inputs, client)
    assert calls == ['persona','time','events','agents']
    assert result == engine.generate('simulation', inputs, client)
    workflow = {'id':'a'*32, 'kind':'simulation', 'resource':state.simulation_id, 'inputs':inputs, 'result':result}
    engine.apply(workflow)
    manager = SimulationManager()  # API consumers instantiate a manager per request.
    assert manager.get_simulation(state.simulation_id).status.value == 'ready'
    assert manager.get_profiles(state.simulation_id, 'reddit')[0]['username'] == result['profiles'][0]['user_name']
    config = manager.get_simulation_config(state.simulation_id)
    assert config['agent_configs'][0]['entity_uuid'] == 'alice'
    assert config['event_config']['initial_posts'][0]['poster_agent_id'] == 0
    before = {p.name:p.read_bytes() for p in (tmp_path / state.simulation_id).iterdir()}
    engine.apply(workflow)
    assert before == {p.name:p.read_bytes() for p in (tmp_path / state.simulation_id).iterdir()}


@pytest.mark.parametrize('kind', ['time','events','agents'])
def test_simulation_rejects_output_for_unknown_or_missing_agents(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path))
    state = SimulationManager().create_simulation('proj_abcdef', 'graph-fixture', True, True)
    results = deepcopy(RESULTS)
    results['time']['agents_per_hour_max'] = 2
    results['events']['initial_posts'][0]['poster_type'] = 'Unknown'
    results['agents']['agent_configs'][0]['agent_id'] = 1
    client = SimpleNamespace(model='gpt-6.1-sol', chat_json=lambda messages, **kw:
        (results if kw['purpose']==kind else RESULTS)[kw['purpose']])
    with pytest.raises(ValueError):
        SetupEngine().generate('simulation', simulation_inputs(state), client)
