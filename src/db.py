import sqlite3
from typing import Optional, List, Dict, Any

def init_db():
    """Initialize the database with required tables."""
    conn = sqlite3.connect('data/foodlog.db')
    c = conn.cursor()
    
    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create food_entries table
    c.execute('''
        CREATE TABLE IF NOT EXISTS food_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            description TEXT,
            calories INTEGER,
            image_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_or_create_user(telegram_id: int, username: Optional[str] = None) -> int:
    """Get or create a user and return their telegram_id."""
    conn = sqlite3.connect('data/foodlog.db')
    c = conn.cursor()
    
    c.execute('SELECT telegram_id FROM users WHERE telegram_id = ?', (telegram_id,))
    result = c.fetchone()
    
    if not result:
        c.execute('INSERT INTO users (telegram_id, username) VALUES (?, ?)',
                 (telegram_id, username))
        conn.commit()
    
    conn.close()
    return telegram_id

def add_food_entry(user_id: int, description: str, calories: int, image_path: Optional[str] = None) -> int:
    """Add a new food entry and return its ID."""
    conn = sqlite3.connect('data/foodlog.db')
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO food_entries (user_id, description, calories, image_path)
        VALUES (?, ?, ?, ?)
    ''', (user_id, description, calories, image_path))
    
    entry_id = c.lastrowid
    conn.commit()
    conn.close()
    return entry_id

def update_food_entry(entry_id: int, description: Optional[str] = None, 
                     calories: Optional[int] = None) -> bool:
    """Update an existing food entry."""
    conn = sqlite3.connect('data/foodlog.db')
    c = conn.cursor()
    
    updates = []
    params = []
    if description is not None:
        updates.append('description = ?')
        params.append(description)
    if calories is not None:
        updates.append('calories = ?')
        params.append(calories)
    
    if not updates:
        conn.close()
        return False
    
    params.append(entry_id)
    query = f'''
        UPDATE food_entries 
        SET {', '.join(updates)}
        WHERE id = ?
    '''
    
    c.execute(query, params)
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success

def delete_food_entry(entry_id: int) -> bool:
    """Delete a food entry."""
    conn = sqlite3.connect('data/foodlog.db')
    c = conn.cursor()
    
    c.execute('DELETE FROM food_entries WHERE id = ?', (entry_id,))
    success = c.rowcount > 0
    conn.commit()
    conn.close()
    return success

def get_user_entries(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent food entries for a user."""
    conn = sqlite3.connect('data/foodlog.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT id, description, calories, image_path, created_at
        FROM food_entries
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit))
    
    entries = []
    for row in c.fetchall():
        entries.append({
            'id': row[0],
            'description': row[1],
            'calories': row[2],
            'image_path': row[3],
            'created_at': row[4]
        })
    
    conn.close()
    return entries 