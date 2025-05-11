import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

logger = logging.getLogger(__name__)


def init_db():
    """Initialize the database with required tables."""
    logger.info("Initializing database")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    # Create users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create food_entries table
    c.execute("""
        CREATE TABLE IF NOT EXISTS food_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            description TEXT,
            calories INTEGER,
            image_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id)
        )
    """)

    # Create messages table for conversation history
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")


def get_or_create_user(telegram_id: int, username: Optional[str] = None) -> int:
    """Get or create a user and return their telegram_id."""
    logger.info(f"Getting/creating user {telegram_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    c.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,))
    result = c.fetchone()

    if not result:
        logger.info(f"Creating new user {telegram_id}")
        c.execute(
            "INSERT INTO users (telegram_id, username) VALUES (?, ?)",
            (telegram_id, username),
        )
        conn.commit()

    conn.close()
    return telegram_id


def add_food_entry(
    user_id: int, description: str, calories: int, image_path: Optional[str] = None
) -> int:
    """Add a new food entry and return its ID."""
    logger.info(
        f"Adding food entry for user {user_id}: {description} ({calories} calories)"
    )
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO food_entries (user_id, description, calories, image_path)
        VALUES (?, ?, ?, ?)
    """,
        (user_id, description, calories, image_path),
    )

    entry_id = c.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Food entry added with ID {entry_id}")
    return entry_id


ADD_FOOD_ENTRY_TOOL = {
    "name": "add_food_entry",
    "type": "function",
    "description": "Add a new food entry to the database.",
    "strict": True,
    "parameters": {
        "type": "object",
        "required": [
            "description",
            "calories",
        ],
        "properties": {
            "description": {
                "type": "string",
                "description": "A description of the food item",
            },
            "calories": {
                "type": "number",
                "description": "The (estimated) number of calories in the food item",
            },
        },
        "additionalProperties": False,
    },
}


def update_food_entry(
    entry_id: int, description: Optional[str] = None, calories: Optional[int] = None
) -> bool:
    """Update an existing food entry."""
    logger.info(f"Updating food entry {entry_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    updates = []
    params = []
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if calories is not None:
        updates.append("calories = ?")
        params.append(calories)

    if not updates:
        conn.close()
        return False

    params.append(entry_id)
    query = f"""
        UPDATE food_entries 
        SET {", ".join(updates)}
        WHERE id = ?
    """

    c.execute(query, params)
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    logger.info(f"Food entry {entry_id} update {'successful' if success else 'failed'}")
    return success


def delete_food_entry(entry_id: int) -> bool:
    """Delete a food entry."""
    logger.info(f"Deleting food entry {entry_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    c.execute("DELETE FROM food_entries WHERE id = ?", (entry_id,))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    logger.info(
        f"Food entry {entry_id} deletion {'successful' if success else 'failed'}"
    )
    return success


def get_user_entries(
    user_id: int, limit: int | Literal["today"] = "today"
) -> List[Dict[str, Any]]:
    """Get recent food entries for a user."""
    logger.info(f"Getting recent entries for user {user_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    if limit == "today":
        # Get entries from today only
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute(
            """
            SELECT id, description, calories, image_path, created_at
            FROM food_entries
            WHERE user_id = ? AND date(created_at) = ?
            ORDER BY created_at DESC
            """,
            (user_id, today),
        )
    else:
        # Get entries with a numeric limit
        c.execute(
            """
            SELECT id, description, calories, image_path, created_at
            FROM food_entries
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )

    entries = []
    for row in c.fetchall():
        entries.append(
            {
                "id": row[0],
                "description": row[1],
                "calories": row[2],
                "image_path": row[3],
                "created_at": row[4],
            }
        )

    conn.close()
    logger.info(f"Retrieved {len(entries)} entries for user {user_id}")
    return entries


def add_message(user_id: int, messages_json_str: str) -> int:
    """Add a list of Pydantic AI messages (as a JSON string) to the conversation history."""
    logger.info(f"Adding Pydantic AI messages for user {user_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO messages (user_id, message_json)
        VALUES (?, ?)
    """,
        (user_id, messages_json_str),
    )

    message_id = c.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Pydantic AI messages stored with ID {message_id}")
    return message_id


def get_conversation_history(user_id: int, limit: int = 10) -> List[ModelMessage]:
    """Get recent conversation history for a user as a list of Pydantic AI ModelMessage objects."""
    logger.info(f"Getting Pydantic AI conversation history for user {user_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    # Fetch the most recent 'limit' entries (each entry is a list of messages from an interaction)
    c.execute(
        """
        SELECT message_json
        FROM messages
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ? 
    """,
        (user_id, limit),
    )

    all_messages: List[ModelMessage] = []
    # Rows are fetched in reverse chronological order (newest first)
    # To maintain chronological order for the agent, we should process them and then reverse if needed,
    # or build the list in reverse.
    # Pydantic AI expects history oldest to newest. So we fetch DESC and then reverse the final list of lists before flattening.

    rows = c.fetchall()
    conn.close()

    # Rows are (message_json_str,)
    # We want to construct the history in chronological order (oldest first for Pydantic AI)
    # So, we iterate through fetched rows (newest first) and prepend to maintain order, or reverse later.

    # Let's build it newest first, then reverse the list of lists of messages, then flatten.
    # No, easier: fetch rows, then reverse the rows list, then process.

    for row in reversed(rows):  # Process oldest first
        message_json_str = row[0]
        try:
            # Each message_json_str is a list of ModelMessage objects
            messages_from_row = ModelMessagesTypeAdapter.validate_json(message_json_str)
            all_messages.extend(messages_from_row)
        except Exception as e:
            logger.error(
                f"Failed to parse message_json for user {user_id}: {e} - JSON: {message_json_str}"
            )
            # Decide how to handle: skip this entry, raise, etc.
            # For now, we'll skip corrupted entries.
            continue

    logger.info(
        f"Retrieved {len(all_messages)} Pydantic AI messages for user {user_id}"
    )
    return all_messages
