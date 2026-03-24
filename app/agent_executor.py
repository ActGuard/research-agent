import logging
import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact,
    Message,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
    UnsupportedOperationError,
)

from app.researcher.errors import BudgetExhaustedError
from app.researcher.graph import run_research

logger = logging.getLogger(__name__)


class ResearchAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        query = context.get_user_input()
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        logger.info("Execute started — task_id=%s query=%s", task_id, query[:120])

        # Signal that work has started
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                taskId=task_id,
                contextId=context_id,
                status=TaskStatus(state=TaskState.working),
                final=False,
            )
        )

        try:
            report = await run_research(query)
        except BudgetExhaustedError as exc:
            logger.warning("Budget exceeded — task_id=%s: %s", task_id, exc)
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    taskId=task_id,
                    contextId=context_id,
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=Message(
                            message_id=str(uuid.uuid4()),
                            role=Role.agent,
                            parts=[TextPart(text=str(exc))],
                        ),
                    ),
                    final=True,
                )
            )
            return
        except Exception:
            logger.exception("Research failed — task_id=%s", task_id)
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    taskId=task_id,
                    contextId=context_id,
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=Message(
                            message_id=str(uuid.uuid4()),
                            role=Role.agent,
                            parts=[TextPart(text="Research failed due to an internal error.")],
                        ),
                    ),
                    final=True,
                )
            )
            return

        # Send the report as an artifact
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                taskId=task_id,
                contextId=context_id,
                artifact=Artifact(
                    artifactId=str(uuid.uuid4()),
                    parts=[TextPart(text=report)],
                    name="Research Report",
                    description=f"Research report for: {query[:100]}",
                ),
            )
        )

        logger.info("Research completed — task_id=%s", task_id)

        # Signal completion
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                taskId=task_id,
                contextId=context_id,
                status=TaskStatus(state=TaskState.completed),
                final=True,
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError()
