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

    # Create interactions table for conversation history
    c.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            interaction_json TEXT,
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
        print(today)
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


def add_interaction(user_id: int, interaction_json_str: str) -> int:
    """Add a Pydantic AI interaction (as a JSON string) to the conversation history."""
    logger.info(f"Adding Pydantic AI interaction for user {user_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO interactions (user_id, interaction_json)
        VALUES (?, ?)
    """,
        (user_id, interaction_json_str),
    )

    interaction_id = c.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Pydantic AI interaction stored with ID {interaction_id}")
    return interaction_id


def get_conversation_history(user_id: int, limit: int = 10) -> List[ModelMessage]:
    """Get recent conversation history for a user as a list of Pydantic AI ModelMessage objects."""
    logger.info(f"Getting Pydantic AI interaction history for user {user_id}")
    conn = sqlite3.connect("data/foodlog.db")
    c = conn.cursor()

    c.execute(
        """
        SELECT interaction_json
        FROM interactions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ? 
    """,
        (user_id, limit),
    )

    all_messages: List[ModelMessage] = []

    rows = c.fetchall()
    conn.close()

    for row in reversed(rows):  # Process oldest first
        interaction_json_str = row[0]
        try:
            # Each interaction_json_str is a list of ModelMessage objects
            messages_from_row = ModelMessagesTypeAdapter.validate_json(
                interaction_json_str
            )
            all_messages.extend(messages_from_row)
        except Exception as e:
            logger.error(
                f"Failed to parse interaction_json for user {user_id}: {e} - JSON: {interaction_json_str}"
            )
            continue

    logger.info(
        f"Retrieved {len(all_messages)} Pydantic AI messages for user {user_id}"
    )
    return all_messages


if __name__ == "__main__":
    print(get_user_entries(553954347))
