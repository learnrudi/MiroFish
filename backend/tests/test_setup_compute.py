from unittest.mock import Mock
import pytest

from app.agent_runners.native_compute import NativeCompute
from test_native_compute import config, receipt_fixture
from app.agent_runners.native_coordinator import digest


def test_setup_response_keeps_request_binding_without_oasis_action(tmp_path):
    record = receipt_fixture(tmp_path)[0]
    record['response_kind'] = 'setup_json'
    response = {'schema_version': 1, 'request_sha256': record['request_sha256'],
                'result': {'analysis_summary': 'A synthetic ontology'}}
    compute = NativeCompute(config(tmp_path))
    compute.call = Mock(return_value={'status':'succeeded', 'response':response})
    assert compute.inspect(record)['response'] == response
    response['request_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        compute.inspect(record)


def test_setup_task_has_exact_reviewed_json_contract_and_existing_identity(tmp_path):
    compute = NativeCompute(config(tmp_path))
    packet = {'schema_version':1, 'kind':'ontology', 'messages':[{'role':'user','content':'Fictional pricing scenario'}]}
    packet['request_sha256'] = digest(packet)
    record = compute.build_record('mfs-' + 'a' * 32 + '-001', 'ontology', packet, 'b' * 64)
    assert record['response_kind'] == 'setup_json'
    assert record['profile']['account'] == compute.config['target']['account']
    assert record['profile']['model'] == 'gpt-6.1-sol'
    assert record['profile']['reasoning_effort'] == 'low'
    assert record['task']['recurrence'] == {'kind':'manual'}
    assert '16384' in record['instructions_text']
    assert packet['request_sha256'] in record['instructions_text']
