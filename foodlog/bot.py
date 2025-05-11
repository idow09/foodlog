import base64
import logging
from dataclasses import dataclass
from datetime import datetime

from pydantic_ai import Agent, BinaryContent, RunContext
from pydantic_ai.messages import ModelMessage

from foodlog.db import (
    add_food_entry as db_add_food_entry,
)
from foodlog.db import (
    add_message,
    get_conversation_history,
    get_or_create_user,
    get_user_entries,
)
from foodlog.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class Deps:
    user_id: int
    image_path: str | None = None


agent: Agent[Deps, str] = Agent(
    model="openai:gpt-4o",
    output_type=str,
    deps_type=Deps,
    end_strategy="exhaustive",
    instrument=True,
)


@agent.tool
async def add_food_entry(ctx: RunContext[Deps], description: str, calories: int):
    """
    Add a new food entry to the user's food log.

    Args:
        description: The description of the food entry.
        calories: The calories of the food entry in kcal.
    """
    db_add_food_entry(ctx.deps.user_id, description, calories, ctx.deps.image_path)


@agent.instructions
async def dynamic_instructions(ctx: RunContext[Deps]) -> str:
    return (
        SYSTEM_PROMPT
        + "\nDon't call multiple tools"
        + f"\n<dev_info>timestamp: {datetime.now()}</dev_info>"
    )


def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    return encoded_string


def daily_summary(user_id: int) -> str:
    entries = get_user_entries(user_id, limit="today")
    if not entries:
        return "No entries for today yet."
    total_calories = sum(entry["calories"] for entry in entries)
    return f"Total calories for today: {total_calories} kcal."


async def process_message(
    user_id: int, text: str | None = None, image_path: str | None = None
) -> str:
    logger.info(
        f"Processing message for user {user_id} with Pydantic-AI native history"
    )

    get_or_create_user(user_id)

    retrieved_history: list[ModelMessage] = get_conversation_history(
        user_id, limit=5
    )  # limit is in interactions, not messages

    agent_input_content: list[dict] = []
    if text:
        agent_input_content.append(text)
    if image_path:
        with open(image_path, "rb") as image_file:
            image_binary = image_file.read()
        agent_input_content.append(
            BinaryContent(data=image_binary, media_type="image/jpeg")
        )
    deps = Deps(user_id=user_id, image_path=image_path)

    logger.info(
        f"Running Pydantic-AI agent for user {user_id} with {len(retrieved_history)} history messages."
    )

    result = await agent.run(
        agent_input_content, message_history=retrieved_history, deps=deps
    )

    add_message(user_id, result.new_messages_json())

    logger.info(f"Assistant message for user {user_id}: {result.output}")
    return result.output + "\n" + daily_summary(user_id)
