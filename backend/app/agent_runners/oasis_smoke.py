"""One bounded OASIS round with one or three agents in fresh SQLite state."""

import asyncio
import os
import sqlite3
from pathlib import Path

import oasis
from camel.prompts import TextPrompt
from oasis.social_agent import AgentGraph, SocialAgent
from oasis.social_platform.config import UserInfo

PERSONA = (
    "You are Alice, a polite, budget-conscious customer. Budget $25 per month. "
    "Your note-taking service has announced a monthly price increase from $20 to $30 "
    "starting next month, with no explanation or new features stated. "
    "Write one original reaction, at most 280 characters, consistent with these facts. "
    "Use the create_post tool exactly once. This is a fictional sandbox; "
    "do not claim to have contacted a real company."
)

GROUP_PERSONAS = (
    ("Alice", PERSONA),
    ("Bob", (
        "You are Bob, a customer who uses the note-taking service daily for work. "
        "Budget $50 per month. The service has announced a monthly price increase "
        "from $20 to $30 starting next month, with no explanation or new features stated. "
        "Write one original reaction, at most 280 characters, consistent with these facts. "
        "Use the create_post tool exactly once. This is a fictional sandbox; "
        "do not claim to have contacted a real company."
    )),
    ("Casey", (
        "You are Casey, an administrator evaluating this note-taking service for your team. "
        "You need predictable costs and want to understand migration effort before deciding. "
        "The service has announced a monthly price increase from $20 to $30 starting "
        "next month, with no explanation or new features stated. Team size and plan terms "
        "are unknown; do not invent them. Write one original reaction, at most 280 characters, "
        "consistent with these facts. Use the create_post tool exactly once. "
        "This is a fictional sandbox; do not claim to have contacted a real company."
    )),
)


async def run_one_agent(model, database):
    """Run a single LLMAction; refuse existing databases instead of appending."""
    result = await _run_agents([model], GROUP_PERSONAS[:1], database)
    return {"posts": [post["content"] for post in result["posts"]],
            "create_post_count": result["create_post_count"]}


async def run_group(models, database):
    """Run three separate personas in one world, one action each, concurrency one."""
    if len(models) != 3 or len({id(model) for model in models}) != 3:
        raise ValueError("The group requires three distinct model instances")
    return await _run_agents(models, GROUP_PERSONAS, database)


async def _run_agents(models, personas, database):
    database = Path(database)
    descriptor = os.open(database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    graph = AgentGraph()
    agents = []
    for agent_id, (model, (name, persona)) in enumerate(zip(models, personas, strict=True)):
        agent = SocialAgent(
            agent_id=agent_id,
            user_info=UserInfo(user_name=name.lower(), name=name, description="Synthetic customer",
                               profile={"persona": persona}),
            user_info_template=TextPrompt("{persona}"),
            model=model, available_actions=[oasis.ActionType.CREATE_POST], max_iteration=1,
        )
        graph.add_agent(agent)
        agents.append(agent)
    # Reddit's local ranking avoids Twitter's embedding-model download.
    env = oasis.make(agent_graph=graph, platform=oasis.DefaultPlatformType.REDDIT,
                     database_path=str(database), semaphore=1)
    try:
        await asyncio.wait_for(env.reset(), 10)
        await asyncio.wait_for(env.step({agent: oasis.LLMAction() for agent in agents}), 30)
    finally:
        try:
            await asyncio.wait_for(env.close(), 5)
        finally:
            env.platform.db.close()
    with sqlite3.connect(database) as conn:
        posts = conn.execute(
            "SELECT u.user_name, p.content FROM post p JOIN user u ON u.user_id=p.user_id "
            "ORDER BY u.user_name").fetchall()
        actions = conn.execute(
            "SELECT u.user_name FROM trace t JOIN user u ON u.user_id=t.user_id "
            "WHERE t.action='create_post' ORDER BY u.user_name").fetchall()
    for model in models:
        if model.last_error is not None:
            raise model.last_error
    expected = sorted(name.lower() for name, _ in personas)
    if [row[0] for row in posts] != expected or [row[0] for row in actions] != expected:
        raise RuntimeError("OASIS did not persist exactly one create_post per agent")
    return {"posts": [{"user_name": name, "content": content} for name, content in posts],
            "create_post_count": len(actions)}
