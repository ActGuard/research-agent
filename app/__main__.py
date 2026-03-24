import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

import uvicorn
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from app.agent_executor import ResearchAgentExecutor
from app.config import settings

agent_card = AgentCard(
    name="Research Agent",
    description=(
        "An AI research agent that accepts a research query and returns "
        "a comprehensive, well-sourced markdown report."
    ),
    version="0.1.0",
    url=f"http://{settings.host}:{settings.port}/",
    capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    skills=[
        AgentSkill(
            id="deep-research",
            name="Deep Research",
            description=(
                "Conducts multi-step research on a topic: plans sub-queries, "
                "searches the web, scrapes and analyzes sources, and writes "
                "a comprehensive markdown report."
            ),
            tags=["research", "report", "web-search"],
        )
    ],
)

handler = DefaultRequestHandler(
    agent_executor=ResearchAgentExecutor(),
    task_store=InMemoryTaskStore(),
)

app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
starlette_app = app.build()

from app.a2a_auth import HMACAuthMiddleware, load_auth_config

auth_config = load_auth_config()
starlette_app.add_middleware(HMACAuthMiddleware, auth_config=auth_config)

if __name__ == "__main__":
    uvicorn.run(starlette_app, host=settings.host, port=settings.port)
