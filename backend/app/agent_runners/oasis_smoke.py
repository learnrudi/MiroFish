"""One real OASIS agent, one tool call, a fresh SQLite database."""

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


async def run_one_agent(model, database):
    """Run a single LLMAction; refuse existing databases instead of appending."""
    database = Path(database)
    descriptor = os.open(database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    graph = AgentGraph()
    agent = SocialAgent(
        agent_id=0,
        user_info=UserInfo(user_name="alice", name="Alice", description="Synthetic customer",
                           profile={"persona": PERSONA}),
        user_info_template=TextPrompt("{persona}"),
        model=model, available_actions=[oasis.ActionType.CREATE_POST], max_iteration=1,
    )
    graph.add_agent(agent)
    # Reddit's local ranking avoids Twitter's embedding-model download.
    env = oasis.make(agent_graph=graph, platform=oasis.DefaultPlatformType.REDDIT,
                     database_path=str(database), semaphore=1)
    try:
        await asyncio.wait_for(env.reset(), 10)
        await asyncio.wait_for(env.step({agent: oasis.LLMAction()}), 30)
    finally:
        try:
            await asyncio.wait_for(env.close(), 5)
        finally:
            env.platform.db.close()
    with sqlite3.connect(database) as conn:
        posts = conn.execute("SELECT content FROM post ORDER BY post_id").fetchall()
        actions = conn.execute("SELECT action FROM trace WHERE action = 'create_post'").fetchall()
    if model.last_error is not None:
        raise model.last_error
    if len(posts) != 1 or len(actions) != 1:
        raise RuntimeError("OASIS did not persist exactly one create_post action")
    return {"posts": [row[0] for row in posts], "create_post_count": len(actions)}
