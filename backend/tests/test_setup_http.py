import io
import os
import pytest

from app import create_app
from app.agent_runners.setup_coordinator import SetupCoordinator
from app.agent_runners.setup_engine import SetupEngine
from app.config import Config
from app.models.project import ProjectManager
from app.models.project import ProjectStatus
from app.services.simulation_manager import SimulationManager
from app.services.zep_entity_reader import EntityNode, FilteredEntities
from types import SimpleNamespace
from unittest.mock import Mock
from test_setup_coordinator import Compute, until
from test_setup_validation import RESULTS


class FixtureCompute(Compute):
    def inspect(self, record):
        result = super().inspect(record)
        if result['status'] == 'succeeded':
            result['response']['result'] = RESULTS[record['packet']['kind']]
        return result


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectManager, 'PROJECTS_DIR', str(tmp_path / 'projects'))
    monkeypatch.setattr(SimulationManager, 'SIMULATION_DATA_DIR', str(tmp_path / 'simulations'))
    monkeypatch.setattr(Config, 'OASIS_SIMULATION_DATA_DIR', SimulationManager.SIMULATION_DATA_DIR)
    monkeypatch.setattr(Config, 'ZEP_API_KEY', None)
    monkeypatch.setattr(Config, 'LLM_API_KEY', None)
    c = SetupCoordinator(tmp_path / 'state', SetupEngine(), FixtureCompute())
    app = create_app(setup_coordinator=c, native_options={'port':5003, 'origins':['http://127.0.0.1:5181']})
    return app.test_client(), c


BASE = 'http://127.0.0.1:5003'


def upload(client, token, text=b'Fictional service raises price from $20 to $30.'):
    return client.post('/api/graph/ontology/generate', base_url=BASE, headers={'X-Native-Token':token}, data={
        'request_id':'a'*32, 'files':(io.BytesIO(text),'scenario.txt'),
        'simulation_requirement':'Explore reactions', 'project_name':'Fictional pricing'})


def test_normal_upload_pauses_for_exact_review_then_populates_project(api):
    client, c = api
    token = client.get('/api/native-setup/session', base_url=BASE).json['data']['token']
    assert upload(client, '').status_code == 403
    started = upload(client, token)
    assert started.status_code == 202
    assert upload(client, token).json == started.json
    assert upload(client, token, b'Changed inputs').status_code == 409
    wid = started.json['data']['setup']['id']
    w = until(c, wid, 'awaiting_approval')
    assert not c.compute.admitted
    review = client.get(f'/api/native-setup/{wid}/review', base_url=BASE).json['data']
    response = client.post(f'/api/native-setup/{wid}/approve', base_url=BASE,
        headers={'X-Native-Token':token}, json={'review_hash':review['sha256']})
    assert response.status_code == 200
    until(c, wid, 'completed')
    project = client.get(f"/api/graph/project/{w['resource']}", base_url=BASE).json['data']
    assert project['status'] == 'ontology_generated' and project['ontology']['entity_types']
    assert len(c.compute.admitted) == 1


def test_native_mode_blocks_foreign_origins_and_unconverted_model_paths(api):
    client,c = api
    for base,headers in [('http://evil.test:5003',{}),(BASE,{'Origin':'https://evil.test'}),
                         (BASE,{'Sec-Fetch-Site':'cross-site'})]:
        assert client.get('/api/native-setup/session',base_url=base,headers=headers).status_code == 403
    token=client.get('/api/native-setup/session',base_url=BASE).json['data']['token']
    for path in ['/api/simulation/start','/api/simulation/interview','/api/simulation/generate-profiles',
                 '/api/report/generate','/api/report/chat','/api/graph/build','/api/simulation/prepare']:
        response=client.post(path,base_url=BASE,headers={'X-Native-Token':token},json={})
        assert response.status_code == 409
    assert not c.compute.admitted


def test_upload_recovers_extracted_text_after_interrupted_project_write(api, monkeypatch):
    client,c=api
    token=client.get('/api/native-setup/session',base_url=BASE).json['data']['token']
    original=os.replace
    def interrupt_text(source,destination):
        if str(destination).endswith('extracted_text.txt'): raise OSError('Interrupted write')
        return original(source,destination)
    monkeypatch.setattr(os,'replace',interrupt_text)
    assert upload(client,token).status_code==503
    monkeypatch.setattr(os,'replace',original)
    assert upload(client,token).status_code==202
    assert ProjectManager.get_extracted_text('proj_'+'a'*32)
    assert len(c.list())==1 and not c.compute.admitted


def test_simulation_prepare_snapshots_graph_once_and_exposes_durable_progress(api, monkeypatch):
    client, c = api
    token = client.get('/api/native-setup/session', base_url=BASE).json['data']['token']
    headers = {'X-Native-Token':token}
    project = ProjectManager.create_project('Pricing')
    project.graph_id, project.status = 'fixture-graph', ProjectStatus.GRAPH_COMPLETED
    project.simulation_requirement = 'Explore customer reactions'
    ProjectManager.save_project(project)
    ProjectManager.save_extracted_text(project.project_id, 'Fictional price change')
    monkeypatch.setattr(Config, 'ZEP_API_KEY', 'fixture-only')
    entity = EntityNode('alice','Alice',['Customer'],'Customer',{})
    reader = Mock(return_value=FilteredEntities([entity], {'Customer'}, 1, 1))
    monkeypatch.setattr('app.services.zep_entity_reader.ZepEntityReader.filter_defined_entities', reader)
    monkeypatch.setattr('app.services.oasis_profile_generator.OasisProfileGenerator._build_entity_context', lambda *_:'Frozen facts')
    created = client.post('/api/simulation/create', base_url=BASE, headers=headers, json={'project_id':project.project_id})
    assert created.status_code == 200
    sid = created.json['data']['simulation_id']
    args = {'simulation_id':sid, 'use_llm_for_profiles':True, 'parallel_profile_count':5}
    started = client.post('/api/simulation/prepare', base_url=BASE, headers=headers, json=args)
    assert started.status_code == 202
    assert client.post('/api/simulation/prepare', base_url=BASE, headers=headers, json=args).json == started.json
    assert reader.call_count == 1
    wid = started.json['data']['task_id']
    for _ in range(4):
        until(c,wid,'awaiting_approval')
        c.approve(wid,c.review(wid)['sha256'])
        until(c,wid,'generating')
    until(c,wid,'completed')
    status = client.post('/api/simulation/prepare/status',base_url=BASE,headers=headers,json={'simulation_id':sid}).json['data']
    assert status['status']=='completed' and status['already_prepared']
    assert reader.call_count == 1 and len(c.compute.admitted)==4
    assert client.get(f'/api/simulation/{sid}/profiles/realtime',base_url=BASE).status_code == 200
    assert client.get(f'/api/simulation/{sid}/config/realtime',base_url=BASE).status_code == 200
