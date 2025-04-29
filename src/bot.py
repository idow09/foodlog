import os
from typing import Optional, Dict, Any
import json
import logging
from openai import OpenAI
from db import (
    get_or_create_user, add_food_entry, update_food_entry,
    delete_food_entry, add_message,
    get_conversation_history
)
from prompts import SYSTEM_PROMPT, FOOD_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def manage_food_entry(
    user_id: int,
    action: str,
    description: Optional[str] = None,
    calories: Optional[int] = None,
    entry_id: Optional[int] = None,
    image_path: Optional[str] = None
) -> Dict[str, Any]:
    """Manage food entries in the database."""
    logger.info(f"Managing food entry: action={action}, user_id={user_id}")
    if action == "add":
        if not description or calories is None:
            logger.warning("Missing required fields for adding food entry")
            return {"success": False, "error": "Missing required fields"}
        entry_id = add_food_entry(user_id, description, calories, image_path)
        return {"success": True, "entry_id": entry_id}
    
    elif action == "update":
        if not entry_id:
            logger.warning("Missing entry_id for update")
            return {"success": False, "error": "Missing entry_id"}
        success = update_food_entry(entry_id, description, calories)
        return {"success": success}
    
    elif action == "delete":
        if not entry_id:
            logger.warning("Missing entry_id for deletion")
            return {"success": False, "error": "Missing entry_id"}
        success = delete_food_entry(entry_id)
        return {"success": success}
    
    logger.warning(f"Invalid action: {action}")
    return {"success": False, "error": "Invalid action"}

def process_message(
    user_id: int,
    text: Optional[str] = None,
    image_path: Optional[str] = None
) -> str:
    """Process a message from the user and return a response."""
    logger.info(f"Processing message for user {user_id}")
    
    # Ensure user exists in database
    get_or_create_user(user_id)
    
    # Get conversation history
    history = get_conversation_history(user_id, limit=10)
    history.reverse()  # Oldest first
    
    # Prepare the message for GPT-4o
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add conversation history
    for msg in history:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
    
    # Add user message
    user_message = ""
    if text:
        user_message += text + "\n"
    if image_path:
        user_message += "[תמונה של אוכל]"
    
    messages.append({"role": "user", "content": user_message})
    
    # Define the function for managing food entries
    functions = [{
        "name": "manage_food_entry",
        "description": "Manage food entries in the database",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "update", "delete"],
                    "description": "The action to perform"
                },
                "description": {
                    "type": "string",
                    "description": "Description of the food"
                },
                "calories": {
                    "type": "integer",
                    "description": "Number of calories"
                },
                "entry_id": {
                    "type": "integer",
                    "description": "ID of the entry to update/delete"
                },
                "image_path": {
                    "type": "string",
                    "description": "Path to the food image"
                }
            },
            "required": ["action"]
        }
    }]
    
    # If there's an image, first analyze it
    if image_path:
        logger.info("Analyzing image with GPT-4 Vision")
        image_messages = [
            {"role": "system", "content": FOOD_ANALYSIS_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "אנא נתח את התמונה וחשב קלוריות"},
                    {"type": "image_url", "image_url": {"url": f"file://{image_path}"}}
                ]
            }
        ]
        
        image_response = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=image_messages,
            max_tokens=300
        )
        
        try:
            food_data = json.loads(image_response.choices[0].message.content)
            text = f"{text or ''}\n{food_data['description']}\n{food_data['calories']} קלוריות"
            logger.info(f"Image analysis successful: {food_data}")
        except Exception as e:
            logger.error(f"Failed to parse image analysis response: {e}")
            text = f"{text or ''}\n[לא הצלחתי לנתח את התמונה]"
    
    # Get response from GPT-4o
    logger.info("Getting response from GPT-4o")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        functions=functions,
        function_call="auto"
    )
    
    message = response.choices[0].message
    
    # Handle function calls
    if message.function_call:
        logger.info(f"Function call detected: {message.function_call.name}")
        function_args = json.loads(message.function_call.arguments)
        function_args["user_id"] = user_id
        if image_path:
            function_args["image_path"] = image_path
        
        result = manage_food_entry(**function_args)
        
        # Add function result to messages
        messages.append({
            "role": "function",
            "name": message.function_call.name,
            "content": json.dumps(result)
        })
        
        # Get final response
        logger.info("Getting final response after function call")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        final_content = response.choices[0].message.content
    else:
        final_content = message.content
    
    # Store the conversation
    add_message(user_id, "user", user_message, image_path)
    add_message(user_id, "assistant", final_content)
    
    logger.info("Message processing completed")
    return final_content 