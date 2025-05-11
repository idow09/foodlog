import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, List, Optional, Union

from annotated_types import MinLen
from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent, RunContext
from pydantic_ai.messages import ModelMessage
from typing_extensions import TypeAlias

from foodlog.db import (
    add_food_entry,
    add_message,
    get_conversation_history,
    get_or_create_user,
    get_user_entries,
)
from foodlog.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class FoodEntry(BaseModel):
    """Model for adding a new food entry."""

    description: Annotated[str, MinLen(1)] = Field(
        description="The description of the food entry."
    )
    calories: int = Field(description="The calories of the food entry in kcal.")


class FoodEntryList(BaseModel):
    """Model for adding a list of food entries."""

    entries: list[FoodEntry] = Field(
        description="A list of food entries to add to the user's food log."
    )


class TextResponse(BaseModel):
    """Model for a simple text response from the assistant."""

    text: str


Response: TypeAlias = Union[FoodEntryList, TextResponse]


@dataclass
class Deps:
    user_id: int
    image_path: Optional[str] = None


agent: Agent[Deps, Response] = Agent(
    model="openai:gpt-4o",
    output_type=Response,
    deps_type=Deps,
    end_strategy="exhaustive",
    instrument=True,
)


@agent.instructions
async def dynamic_instructions(ctx: RunContext[Deps]) -> str:
    return SYSTEM_PROMPT + f"\n<dev_info>timestamp: {datetime.now()}</dev_info>"


@agent.output_validator
async def validate_and_process_output(
    ctx: RunContext[Deps], output: Response
) -> Response:
    user_id = ctx.deps.user_id
    if isinstance(output, FoodEntryList):
        logger.info(f"Validator: Adding food entries for user {user_id}")
        for entry in output.entries:
            add_food_entry(
                user_id, entry.description, entry.calories, ctx.deps.image_path
            )
        return output
    elif isinstance(output, TextResponse):
        return output


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
    user_id: int, text: Optional[str] = None, image_path: Optional[str] = None
) -> str:
    logger.info(
        f"Processing message for user {user_id} with Pydantic-AI native history"
    )

    get_or_create_user(user_id)

    retrieved_history: List[ModelMessage] = get_conversation_history(
        user_id, limit=10
    )  # `limit` here refers to DB entries, not total messages

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

    assistant_response_text = ""
    if isinstance(result.output, FoodEntryList):
        for fe in result.output.entries:
            assistant_response_text += (
                f"New record: {fe.description} ({fe.calories} calories).\n"
            )
        assistant_response_text += daily_summary(user_id)
    elif isinstance(result.output, TextResponse):
        assistant_response_text = result.output.text

    logger.info(f"Assistant message for user {user_id}: {assistant_response_text}")
    return assistant_response_text
