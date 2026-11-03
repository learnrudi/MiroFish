import pytest
from app.agent_runners.native_http import create_native_app
from app.agent_runners.native_coordinator import NativeCoordinator
from test_native_coordinator import Engine, Compute, advance_until


@pytest.fixture
def api(tmp_path):
    c = NativeCoordinator(tmp_path, Engine(), Compute())
    app = create_native_app(c, {'port': 5001, 'origins': ['http://127.0.0.1:5179']})
    return app.test_client(), c


def test_cross_origin_and_rebound_hosts_cannot_read_operator_session(api):
    client, _ = api
    for base, headers in [
        ('http://evil.test:5001', {}),
        ('http://127.0.0.1:5001', {'Origin': 'https://evil.test'}),
        ('http://127.0.0.1:5001', {'Sec-Fetch-Site': 'cross-site'}),
    ]:
        assert client.get('/api/native-runs/session', base_url=base, headers=headers).status_code == 403
    assert client.get('/api/native-runs/session', base_url='http://127.0.0.1:5001').status_code == 200


def test_ui_start_review_approval_and_refresh_use_durable_state(api):
    client, c = api
    base = 'http://127.0.0.1:5001'
    headers = {'X-Native-Token': client.get('/api/native-runs/session', base_url=base).json['token'],
        'Origin': 'http://127.0.0.1:5179'}
    assert client.post('/api/native-runs', base_url=base, json={'request_id': 'a' * 32}).status_code == 403
    request = {'request_id': 'a' * 32}
    response = client.post('/api/native-runs', base_url=base, headers=headers, json=request)
    assert response.status_code == 200
    assert client.post('/api/native-runs', base_url=base, headers=headers, json=request).json == response.json
    run_id = response.json['id']
    advance_until(c, run_id, 'awaiting_approval')
    review = client.get(f'/api/native-runs/{run_id}/review', base_url=base).json
    response = client.post(f'/api/native-runs/{run_id}/approve', base_url=base, headers=headers, json={'review_hash': review['sha256']})
    assert response.json['status'] == 'queued'
    snapshot = client.get('/api/native-runs/session', base_url=base).json['run']
    assert snapshot['id'] == run_id
    assert 'rounds' not in snapshot and 'packets' not in str(snapshot)
    assert c.compute.admissions == []
    assert client.post('/api/native-runs', base_url=base, headers=headers, json={**request, 'model': 'another'}).status_code == 400
