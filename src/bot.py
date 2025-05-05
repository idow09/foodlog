import base64
from datetime import datetime
from typing import Optional
import logging
from run_context import UserMessageCtx
from db import (
    add_food_entry, delete_food_entry, get_or_create_user, add_message,
    get_conversation_history, get_user_entries, update_food_entry
)
from prompts import SYSTEM_PROMPT
from agents import Agent, RunContextWrapper, Runner

logger = logging.getLogger(__name__)


def dynamic_instructions(wrapper: RunContextWrapper[UserMessageCtx], agent: Agent[UserMessageCtx]):
    return SYSTEM_PROMPT + f"\n<dev_info>user_id: {wrapper.context.user_id}; timestamp: {datetime.now()}</dev_info>"

agent = Agent[UserMessageCtx](name="FoodLogger", model="gpt-4o", instructions=dynamic_instructions, tools=[
    add_food_entry,
    # update_food_entry,
    # delete_food_entry,
    # get_user_entries
])

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    return encoded_string

async def process_message(
    user_id: int,
    text: Optional[str] = None,
    image_path: Optional[str] = None
) -> str:
    orig_user_message_ctx = UserMessageCtx(user_id=user_id, timestamp=datetime.now(), image_path=image_path)
    
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

    result = await Runner.run(starting_agent=agent, input=messages, context=orig_user_message_ctx)
    assistant_message = result.final_output
    for item in result.new_items:
        add_message(user_id, item.to_input_item())

    logger.info("Message processing completed")
    return assistant_message