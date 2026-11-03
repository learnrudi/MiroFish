"""Freeze graph data once before any native persona or config generation."""
import uuid

from werkzeug.exceptions import BadRequest
from .setup_coordinator import ReplayClient
from ..models.project import ProjectManager
from ..services.oasis_profile_generator import OasisProfileGenerator
from ..services.simulation_manager import SimulationManager
from ..services.zep_entity_reader import ZepEntityReader
from ..utils.locale import get_locale


def create_simulation(data):
    from .setup_http import identifier
    allowed = {'project_id','graph_id','enable_twitter','enable_reddit'}
    if not isinstance(data,dict) or not set(data)<=allowed:
        raise BadRequest('Invalid simulation creation fields')
    project = ProjectManager.get_project(identifier(data.get('project_id'),'proj_'))
    if project is None or not project.graph_id or project.status.value != 'graph_completed':
        raise ValueError('A completed project graph is required')
    if data.get('graph_id',project.graph_id) != project.graph_id:
        raise ValueError('Graph must belong to the project')
    flags = [data.get(key,True) for key in ('enable_twitter','enable_reddit')]
    if any(type(flag) is not bool for flag in flags) or not any(flags):
        raise BadRequest('Select at least one platform')
    manager = SimulationManager()
    for state in manager.list_simulations(project.project_id):
        if [state.enable_twitter,state.enable_reddit] == flags and state.graph_id == project.graph_id:
            return state.to_dict()
    return manager.create_simulation(project.project_id,project.graph_id,*flags).to_dict()


def prepare(coordinator, data):
    from .setup_http import identifier
    allowed = {'simulation_id','use_llm_for_profiles','parallel_profile_count','defined_entity_types','force_regenerate'}
    if not isinstance(data,dict) or not set(data)<=allowed or data.get('use_llm_for_profiles',True) is not True or data.get('force_regenerate',False) is not False:
        raise BadRequest('Native setup requires generated personas and preserves existing work')
    sid = identifier(data.get('simulation_id'),'sim_')
    types = data.get('defined_entity_types')
    if types is not None and (not isinstance(types,list) or not 1<=len(types)<=30 or any(not isinstance(t,str) or not 1<=len(t)<=100 for t in types)):
        raise BadRequest('Invalid entity-type selection')
    selection = sorted(set(types)) if types else None
    with coordinator.lock:
        existing = coordinator.for_resource(sid)
        if existing:
            if existing['inputs']['defined_entity_types'] != selection:
                raise ValueError('Entity selection changed')
            return existing
        state = SimulationManager().get_simulation(sid)
        if state is None or state.status.value != 'created':
            raise ValueError('A new simulation is required')
        project = ProjectManager.get_project(state.project_id)
        if project is None or project.graph_id != state.graph_id or project.status.value != 'graph_completed':
            raise ValueError('Project graph changed')
        filtered = ZepEntityReader().filter_defined_entities(state.graph_id, selection, enrich_with_edges=True)
        entities = sorted(filtered.entities, key=lambda entity:entity.uuid)
        if not 1<=len(entities)<=30 or len({e.uuid for e in entities})!=len(entities):
            raise ValueError('Native setup supports 1–30 distinct graph entities')
        generator = OasisProfileGenerator(graph_id=state.graph_id, llm_client=ReplayClient([]))
        inputs = {'state':state.to_dict(), 'entities':[e.to_dict() for e in entities],
                  'entity_contexts':{e.uuid:generator._build_entity_context(e) for e in entities},
                  'defined_entity_types':selection, 'locale':get_locale(),
                  'simulation_requirement':project.simulation_requirement,
                  'document_text':ProjectManager.get_extracted_text(project.project_id) or ''}
        return coordinator.start(uuid.uuid5(uuid.NAMESPACE_URL,'mirofish-native-setup:'+sid).hex,
                                 'simulation',sid,inputs)


def progress(workflow, sid):
    from .setup_http import public
    if workflow is None:
        return {'simulation_id':sid, 'status':'not_started','already_prepared':False,'progress':0}
    total = len(workflow['inputs']['entities']) + 2 + (len(workflow['inputs']['entities'])+19)//20
    done = sum(call['status']=='succeeded' for call in workflow['calls'])
    return {'simulation_id':sid, 'task_id':workflow['id'], 'status':workflow['status'],
            'already_prepared':workflow['status']=='completed',
            'expected_entities_count':len(workflow['inputs']['entities']),
            'progress':100 if workflow['status']=='completed' else min(95,int(done/total*95)),
            'message':workflow['events'][-1]['message'], 'error':(workflow['error'] or {}).get('message'),
            'setup':public(workflow)}
