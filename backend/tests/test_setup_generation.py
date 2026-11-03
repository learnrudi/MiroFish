from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.config import Config
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.simulation_config_generator import SimulationConfigGenerator
from app.services.zep_entity_reader import EntityNode


def test_persona_uses_injected_generation_without_api_or_fallback(monkeypatch):
    monkeypatch.setattr('app.services.oasis_profile_generator.OpenAI', Mock())
    monkeypatch.setattr('time.sleep', lambda _: None)
    generator = OasisProfileGenerator(api_key='test-only', zep_api_key='')
    result = {'bio': 'Budget conscious customer', 'persona': 'Alice compares costs.'}
    generate = Mock(return_value=result)
    generator.llm_client = SimpleNamespace(chat_json=generate)
    actual = generator._generate_profile_with_llm('Alice', 'Person', 'Customer', {}, 'Shared facts')
    assert actual == result
    assert generate.call_count == 1
    generator.client.chat.completions.create.assert_not_called()


@pytest.mark.parametrize('part', ['time', 'events', 'agents'])
def test_native_config_failure_is_preserved_without_fallback(monkeypatch, part):
    monkeypatch.setattr('app.services.simulation_config_generator.OpenAI', Mock())
    monkeypatch.setattr('time.sleep', lambda _: None)
    generator = SimulationConfigGenerator(api_key='test-only')
    failure = RuntimeError('Native review is pending')
    generator.llm_client = SimpleNamespace(chat_json=Mock(side_effect=failure))
    entities = [EntityNode('alice', 'Alice', ['Person'], 'Customer', {})]
    with pytest.raises(RuntimeError, match='Native review is pending'):
        if part == 'time':
            generator._generate_time_config('Facts', 1)
        elif part == 'events':
            generator._generate_event_config('Facts', 'Price change', entities)
        else:
            generator._generate_agent_configs_batch('Facts', entities, 0, 'Price change')
    generator.client.chat.completions.create.assert_not_called()


def test_injected_generators_need_no_model_api_key(monkeypatch):
    monkeypatch.setattr(Config, 'LLM_API_KEY', None)
    monkeypatch.setattr(Config, 'ZEP_API_KEY', None)
    for module in ['oasis_profile_generator', 'simulation_config_generator']:
        monkeypatch.setattr(f'app.services.{module}.OpenAI', Mock(side_effect=AssertionError('API client constructed')))
    client = SimpleNamespace(chat_json=Mock(), model='gpt-6.1-sol')
    persona = OasisProfileGenerator(llm_client=client, entity_contexts={'alice': 'Frozen graph facts'})
    config = SimulationConfigGenerator(llm_client=client)
    assert persona._build_entity_context(EntityNode('alice','Alice',['Person'],'Customer',{})) == 'Frozen graph facts'
    assert config.model_name == 'gpt-6.1-sol'


def test_custom_person_type_uses_individual_persona_prompt():
    generate = Mock(return_value={'bio': 'Independent reviewer', 'persona': 'Fictional Casey.'})
    client = SimpleNamespace(chat_json=generate, model='gpt-6.1-sol')
    generator = OasisProfileGenerator(llm_client=client, entity_contexts={'casey': 'Frozen facts'})
    entity = EntityNode('casey', 'Casey', ['IndependentReviewer'],
                        'An independent reviewer.', {'full_name': 'Casey'})

    generator.generate_profile_from_entity(entity, 0)

    prompt = generate.call_args.kwargs['messages'][1]['content']
    assert '个人记忆' in prompt
    assert '机构基本信息' not in prompt


@pytest.mark.parametrize('entity_type,attributes,individual', [
    ('Customer', {'full_name': 'Alice'}, True),
    ('ProductManager', {'full_name': 'Bob'}, True),
    ('ServiceProvider', {'org_name': 'NotebookCo'}, False),
    ('Organization', {'full_name': 'NotebookCo'}, False),
    ('Person', {}, True),
    ('UnknownRole', {'full_name': '   '}, False),
    ('UnknownRole', {'full_name': ['Casey']}, False),
    ('UnknownRole', {'full_name': 'Casey', 'org_name': 'Review Team'}, False),
    ('UnknownRole', {'full_name': 'Casey', 'org_name': {}}, False),
    ('UnknownRole', None, False),
])
def test_persona_prompt_preserves_type_and_identity_boundaries(entity_type, attributes, individual):
    generate = Mock(return_value={'bio': 'Test account', 'persona': 'Fictional test account.'})
    client = SimpleNamespace(chat_json=generate, model='gpt-6.1-sol')
    generator = OasisProfileGenerator(llm_client=client, entity_contexts={'actor': 'Frozen facts'})
    entity = EntityNode('actor', 'Actor', [entity_type], 'Test actor', attributes)

    generator.generate_profile_from_entity(entity, 0)

    prompt = generate.call_args.kwargs['messages'][1]['content']
    assert ('个人记忆' in prompt) is individual
    assert ('机构基本信息' in prompt) is not individual
