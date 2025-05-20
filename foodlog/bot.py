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
    add_interaction,
    get_conversation_history,
    get_or_create_user,
    get_user_entries,
)
from foodlog.db import (
    delete_food_entry as db_delete_food_entry,
)
from foodlog.db import (
    update_food_entry as db_update_food_entry,
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


@agent.tool
async def update_food_entry(
    ctx: RunContext[Deps], entry_id: int, description: str, calories: int
):
    """
    Update a food entry in the user's food log.

    Args:
        entry_id: The ID of the food entry to update.
        description: The description of the food entry.
        calories: The calories of the food entry in kcal.
    """
    db_update_food_entry(ctx.deps.user_id, entry_id, description, calories)


@agent.tool
async def delete_food_entry(ctx: RunContext[Deps], entry_id: int):
    """
    Delete a food entry from the user's food log.

    Args:
        entry_id: The ID of the food entry to delete.
    """
    db_delete_food_entry(ctx.deps.user_id, entry_id)


@agent.tool
async def get_user_entries_today(ctx: RunContext[Deps]):
    """
    Get all food entries for the user today.
    """
    return get_user_entries(ctx.deps.user_id, limit="today")


@agent.instructions
async def dynamic_instructions(ctx: RunContext[Deps]) -> str:
    return (
        SYSTEM_PROMPT
        + f"\n<dev_info>timestamp: {datetime.now().astimezone().isoformat()}</dev_info>"
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
    goal_calories = 1800  # Magic constant for now
    bar_length = 20  # Length of the progress bar

    progress_ratio = min(total_calories / goal_calories, 1.0)  # Cap at 100% for the bar
    filled_length = int(progress_ratio * bar_length)
    empty_length = bar_length - filled_length

    progress_bar = "█" * filled_length + "░" * empty_length
    percentage = (total_calories / goal_calories) * 100

    progress_display = (
        f"[{progress_bar}] {percentage:.0f}%\n({total_calories}/{goal_calories} kcal)"
    )

    return progress_display


async def handle_command(user_id: int, text: str) -> str:
    logger.info(f"Handling command: {text}")
    if text == "/today":
        return "Here's your food log history for today:\n" + "\n".join(
            [
                f"{entry['description']} - {entry['calories']} kcal"
                for entry in get_user_entries(user_id, limit="today")
            ]
        )
    elif text.startswith("/add "):
        parts = text[5:].split(" ", 1)  # Skip "/add "
        calories = int(parts[0])
        if len(parts) == 1:
            description = ""
        else:
            description = parts[1]
        db_add_food_entry(user_id, description, calories)
        return f"Added {calories} kcal to your food log.\n{daily_summary(user_id)}"
    elif text == "/help":
        return "Here's a list of commands:\n" + "\n".join(
            [
                "/today - Show your food log history for today",
                "/add <calories> <description> - Add a new food entry to your food log",
                "/help - Show this help message",
            ]
        )
    else:
        return "Invalid command. Use /help to see available commands."


async def process_message(
    user_id: int, text: str | None = None, image_path: str | None = None
) -> str:
    logger.info(
        f"Processing message for user {user_id} with Pydantic-AI native history"
    )

    get_or_create_user(user_id)

    if text and text.startswith("/"):
        return await handle_command(user_id, text)

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

    add_interaction(user_id, result.new_messages_json())

    logger.info(f"Assistant message for user {user_id}: {result.output}")
    return result.output + "\n" + daily_summary(user_id)
