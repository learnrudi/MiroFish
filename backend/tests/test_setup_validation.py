import pytest
import copy
from app.agent_runners.setup_validation import validate_result

RESULTS = {
    'ontology': {'entity_types':[{'name':'Customer','description':'A fictional customer','attributes':[]}],
                 'edge_types':[], 'analysis_summary':'Fictional price-change discussion.'},
    'persona': {'bio':'Budget-conscious customer','persona':'Alice compares prices and values export options.',
                'karma':100,'friend_count':20,'follower_count':30,'statuses_count':10},
    'time': {'total_simulation_hours':24,'minutes_per_round':60,'agents_per_hour_min':1,
             'agents_per_hour_max':1,'peak_hours':[19,20],'off_peak_hours':[0,1],
             'morning_hours':[7,8],'work_hours':[9,10]},
    'events': {'initial_posts':[{'content':'A fictional price change is announced.','poster_type':'Customer'}],
               'hot_topics':['pricing'],'narrative_direction':'Compare budgets and migration effort.'},
    'agents': {'agent_configs':[{'agent_id':0,'activity_level':0.5,'posts_per_hour':1,
        'comments_per_hour':1,'active_hours':[9,10],'response_delay_min':5,'response_delay_max':30,
        'sentiment_bias':-0.5,'stance':'opposing','influence_weight':1}]},
}


@pytest.mark.parametrize('kind', ['ontology','persona','time','events','agents'])
def test_empty_native_results_cannot_become_default_setup(kind):
    with pytest.raises(ValueError):
        validate_result(kind, {})


@pytest.mark.parametrize(('kind','field','bad'), [
    ('ontology','entity_types',[]), ('persona','persona',{'unexpected':'object'}),
    ('time','minutes_per_round',0), ('time','peak_hours',[24]),
    ('events','initial_posts',[{'content':4,'poster_type':'Customer'}]),
    ('agents','agent_configs',[{'agent_id':0}]),
])
def test_native_results_validate_consumer_types_and_ranges(kind, field, bad):
    assert validate_result(kind, RESULTS[kind]) == RESULTS[kind]
    changed = copy.deepcopy(RESULTS[kind]); changed[field] = bad
    with pytest.raises(ValueError): validate_result(kind, changed)
