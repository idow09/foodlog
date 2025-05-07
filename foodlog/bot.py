import base64
from datetime import datetime
import json
from typing import Optional
import logging
from foodlog.db import ADD_FOOD_ENTRY_TOOL, add_food_entry, get_or_create_user, add_message, get_conversation_history
from foodlog.prompts import SYSTEM_PROMPT
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

client = AsyncOpenAI()

def system_prompt():
    return (
        SYSTEM_PROMPT
        + f"\n<dev_info>timestamp: {datetime.now()}</dev_info>"
    )



def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    return encoded_string


async def process_message(
    user_id: int, text: Optional[str] = None, image_path: Optional[str] = None
) -> str:
    logger.info(f"Processing message for user {user_id}")

    get_or_create_user(user_id)

    messages = get_conversation_history(user_id, limit=10)
    messages.reverse()

    if image_path:
        b64_image = image_to_base64(image_path)
        image_message = {
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "detail": "auto",
                    "image_url": f"data:image/jpeg;base64,{b64_image}",
                }
            ],
        }

        messages.append(image_message)
        add_message(user_id, image_message)
    if text:
        text_message = {"role": "user", "content": text}
        messages.append(text_message)
        add_message(user_id, text_message)

    logger.info("Getting response from agent")

    response = await client.responses.create(
        model="gpt-4o-mini",
        instructions=system_prompt(),
        input=messages,
        tools=[
            ADD_FOOD_ENTRY_TOOL,
        ],
        tool_choice="auto",
    )
    assistant_message = ""
    for out in response.output:
        if out.type == "function_call":
            tool_call = out
            args = json.loads(tool_call.arguments)
            description, calories = args["description"], args["calories"]
            add_food_entry(user_id, description, calories, image_path)
            assistant_message += f"New record: {description} ({calories} calories)\n"

    if assistant_message:
        add_message(user_id, {"role": "assistant", "content": assistant_message})
        logger.info(f"Assistant message: {assistant_message}")
        logger.info("Message processing completed with new record(s)")
        return assistant_message

    add_message(user_id, {"role": "assistant", "content": response.output_text})
    logger.info(f"Assistant message: {response.output_text}")
    logger.info("Message processing completed with no new record")
    return response.output_text
