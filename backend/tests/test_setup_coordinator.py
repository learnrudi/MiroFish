from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest

from app.agent_runners.setup_coordinator import SetupCoordinator
from app.agent_runners.native_errors import TransportUnavailable


def test_repeated_setup_preserves_one_input_snapshot_across_restart(tmp_path):
    compute = SimpleNamespace(fingerprint=lambda:'source')
    c = SetupCoordinator(tmp_path, None, compute)
    def start(_):
        return c.start('a'*32, 'ontology', 'proj_abc123', {'documents':['Facts']})
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(start, range(4)))
    assert {r['id'] for r in rows} == {'a'*32}
    assert all(r['status']=='generating' and r['calls']==[] for r in rows)
    resumed = SetupCoordinator(tmp_path, None, compute)
    assert resumed.get('a'*32)['inputs'] == {'documents':['Facts']}
    with pytest.raises(ValueError, match='changed'):
        resumed.start('a'*32, 'ontology', 'proj_abc123', {'documents':['Different']})


class Engine:
    def __init__(self):
        self.applied = []

    def generate(self, kind, inputs, client):
        first = client.chat_json([{'role':'user','content':'First request'}])
        second = client.chat_json([{'role':'user','content':'Second request'}])
        return {'values':[first,second]}

    def apply(self, workflow):
        self.applied.append(workflow['result'])


class Compute:
    identity = {'identity':'test-transport','model':'fixture','effort':'low'}
    source = 'source'

    def __init__(self):
        self.admitted = set()

    def fingerprint(self): return self.source
    def prepare(self, task_id, name, packet, source): return {'task_id':task_id, 'packet':packet}
    def verify(self, records): pass
    def admit(self, record): self.admitted.add(record['task_id'])
    def inspect(self, record):
        if record['task_id'] not in self.admitted: return {'status':'prepared'}
        return {'status':'succeeded', 'job_id':record['task_id'], 'response':{
            'schema_version':1, 'request_sha256':record['packet']['request_sha256'], 'result':{'ok':True}}}


def until(c, workflow_id, status):
    for _ in range(20):
        w = c.advance(workflow_id)
        if w['status'] == status: return w
    pytest.fail(f"Expected {status}, got {w['status']}: {w.get('error')}")


def test_each_generation_needs_exact_approval_and_restart_reuses_verified_results(tmp_path):
    compute, engine = Compute(), Engine()
    c = SetupCoordinator(tmp_path, engine, compute)
    w = c.start('b'*32, 'ontology', 'proj_abc124', {})
    for number in range(2):
        w = until(c, w['id'], 'awaiting_approval')
        assert len(compute.admitted) == number
        with pytest.raises(ValueError): c.approve(w['id'], 'wrong')
        review = c.review(w['id'])
        c.approve(w['id'], review['sha256'])
        c.approve(w['id'], review['sha256'])
        c = SetupCoordinator(tmp_path, engine, compute)
        until(c, w['id'], 'generating')
    final = until(c, w['id'], 'completed')
    assert len(compute.admitted) == 2
    assert final['result'] == {'values':[{'ok':True},{'ok':True}]}
    assert engine.applied == [final['result']]


def test_lost_admission_is_reconciled_without_a_second_job(tmp_path):
    class LostReply(Compute):
        def admit(self, record):
            super().admit(record)
            raise TransportUnavailable('Reply lost after admission')
    compute, engine = LostReply(), Engine()
    c = SetupCoordinator(tmp_path, engine, compute)
    w = c.start('c'*32, 'ontology', 'proj_abc125', {})
    w = until(c, w['id'], 'awaiting_approval')
    c.approve(w['id'], c.review(w['id'])['sha256'])
    failed = until(c,w['id'],'failed')
    assert failed['error']['retryable']
    with pytest.raises(ValueError,match='active setup'):
        c.start('e'*32,'ontology','proj_abc999',{})
    resumed = SetupCoordinator(tmp_path, engine, compute)
    resumed.reconcile(w['id'], failed['version'])
    w = until(resumed,w['id'],'generating')
    assert len(compute.admitted)==1 and w['calls'][0]['status']=='succeeded'


def test_unchanged_native_poll_does_not_append_events_or_change_version(tmp_path):
    class Running(Compute):
        def inspect(self, record):
            if record['task_id'] not in self.admitted: return {'status':'prepared'}
            return {'status':'running', 'job_id':'job-one'}
    c = SetupCoordinator(tmp_path,Engine(),Running())
    w = c.start('d'*32,'ontology','proj_abc126',{})
    until(c,w['id'],'awaiting_approval')
    c.approve(w['id'],c.review(w['id'])['sha256'])
    c.advance(w['id'])
    running = c.advance(w['id'])
    assert c.advance(w['id']) == running
