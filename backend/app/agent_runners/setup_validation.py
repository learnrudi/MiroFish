"""Validate native JSON before it becomes application setup data."""
import math

REQUIRED = {
    'ontology': {'entity_types','edge_types','analysis_summary'},
    'persona': {'bio','persona'},
    'time': {'total_simulation_hours','minutes_per_round','agents_per_hour_min','agents_per_hour_max',
             'peak_hours','off_peak_hours','morning_hours','work_hours'},
    'events': {'initial_posts','hot_topics','narrative_direction'},
    'agents': {'agent_configs'},
}


def validate_result(kind, value):
    if kind not in REQUIRED or not isinstance(value, dict) or not REQUIRED[kind] <= value.keys():
        raise ValueError('Incomplete native setup result')
    if kind == 'ontology':
        rows(value['entity_types'], 1, 30)
        rows(value['edge_types'], 0, 60)
        text(value['analysis_summary'])
        for item in value['entity_types'] + value['edge_types']:
            if not isinstance(item, dict): raise ValueError('Ontology entry must be an object')
            text(item.get('name')); text(item.get('description'))
            if 'attributes' in item and not isinstance(item['attributes'], list):
                raise ValueError('Ontology attributes must be a list')
    elif kind == 'persona':
        text(value['bio']); text(value['persona'])
        for key in ('karma','friend_count','follower_count','statuses_count'):
            if key in value: number(value[key],0,100000000,integer=True)
        if value.get('age') is not None: number(value['age'],0,120,integer=True)
        for key in ('gender','mbti','country','profession'):
            if value.get(key) is not None: text(value[key])
        if 'interested_topics' in value:
            rows(value['interested_topics'],0,100)
            for item in value['interested_topics']: text(item)
    elif kind == 'time':
        number(value['total_simulation_hours'],1,168,integer=True)
        number(value['minutes_per_round'],1,120,integer=True)
        number(value['agents_per_hour_min'],1,1000,integer=True)
        number(value['agents_per_hour_max'],value['agents_per_hour_min'],1000,integer=True)
        for key in ('peak_hours','off_peak_hours','morning_hours','work_hours'): hours(value[key])
    elif kind == 'events':
        rows(value['initial_posts'],0,100); rows(value['hot_topics'],0,100)
        text(value['narrative_direction'], empty=True)
        for topic in value['hot_topics']: text(topic)
        for post in value['initial_posts']:
            if not isinstance(post, dict): raise ValueError('Initial post must be an object')
            text(post.get('content')); text(post.get('poster_type'))
    else:
        rows(value['agent_configs'],1,20)
        for agent in value['agent_configs']:
            if not isinstance(agent, dict): raise ValueError('Agent settings must be an object')
            number(agent.get('agent_id'),0,1000,integer=True)
            number(agent.get('activity_level'),0,1)
            for key in ('posts_per_hour','comments_per_hour'): number(agent.get(key),0,100)
            hours(agent.get('active_hours'))
            number(agent.get('response_delay_min'),0,10080)
            number(agent.get('response_delay_max'),agent['response_delay_min'],10080)
            number(agent.get('sentiment_bias'),-1,1)
            number(agent.get('influence_weight'),0,100)
            if agent.get('stance') not in ('supportive','opposing','neutral','observer'):
                raise ValueError('Invalid agent stance')
    return value


def text(value, empty=False):
    if not isinstance(value,str) or len(value)>16000 or (not empty and not value.strip()):
        raise ValueError('Expected bounded setup text')


def number(value, low, high, integer=False):
    if type(value) not in ((int,) if integer else (int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('Setup number is outside its allowed range')


def rows(value, low, high):
    if not isinstance(value,list) or not low<=len(value)<=high:
        raise ValueError('Invalid setup list')


def hours(value):
    rows(value,0,24)
    for hour in value: number(hour,0,23,integer=True)
    if len(set(value))!=len(value): raise ValueError('Duplicate activity hour')
