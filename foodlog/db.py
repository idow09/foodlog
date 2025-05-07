import json
import sqlite3
from typing import Optional, List, Dict, Any
import logging
from agents import RunContextWrapper, function_tool

from run_context import UserMessageCtx

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


@function_tool
def add_food_entry(
    wrapper: RunContextWrapper[UserMessageCtx], description: str, calories: int
) -> int:
    """Add a new food entry and return its ID."""
    logger.info(
        f"Adding food entry for user {wrapper.context.user_id}: {description} ({calories} calories)"
    )
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO food_entries (user_id, description, calories, image_path)
        VALUES (?, ?, ?, ?)
    """,
        (wrapper.context.user_id, description, calories, wrapper.context.image_path),
    )

    entry_id = c.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Food entry added with ID {entry_id}")
    return entry_id


@function_tool
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


@function_tool
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


@function_tool
def get_user_entries(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent food entries for a user."""
    logger.info(f"Getting recent entries for user {user_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

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


def add_message(user_id: int, message_dict: dict) -> int:
    """Add a message to the conversation history."""
    logger.info(f"Adding message for user {user_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO messages (user_id, message_json)
        VALUES (?, ?)
    """,
        (user_id, json.dumps(message_dict)),
    )

    message_id = c.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Message added with ID {message_id}")
    return message_id


def get_conversation_history(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent conversation history for a user."""
    logger.info(f"Getting conversation history for user {user_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    c.execute(
        """
        SELECT message_json, created_at
        FROM messages
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """,
        (user_id, limit),
    )

    messages = []
    for row in c.fetchall():
        messages.append(json.loads(row[0]))

    conn.close()
    logger.info(f"Retrieved {len(messages)} messages for user {user_id}")
    return messages
