import sqlite3
import logging
import os
from datetime import datetime

logger = logging.getLogger("bot.db")

DB_PATH = "bot_data.db"

def get_connection():
    """Creates and returns a connection to the database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn

def setup_database():
    """Create database tables if they don't exist"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Allowlist table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS allowlist (
            user_id INTEGER PRIMARY KEY,
            approved_by INTEGER,
            approved_at TIMESTAMP,
            status TEXT DEFAULT 'pending',
            answers TEXT
        )
        ''')
        
        # Warnings table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            timestamp TIMESTAMP,
            active BOOLEAN DEFAULT TRUE
        )
        ''')
        
        # Bans table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            timestamp TIMESTAMP,
            expires_at TIMESTAMP,
            active BOOLEAN DEFAULT TRUE
        )
        ''')
        
        # Suggestions table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT,
            message_id INTEGER,
            channel_id INTEGER,
            timestamp TIMESTAMP,
            status TEXT DEFAULT 'pending'
        )
        ''')
        
        # Allowlist questions table to store custom questions
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS allowlist_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            required BOOLEAN DEFAULT TRUE,
            order_num INTEGER
        )
        ''')
        
        # Temporary channels table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS temp_channels (
            channel_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            created_at TIMESTAMP,
            purpose TEXT
        )
        ''')
        
        conn.commit()
        logger.info("Database setup completed")
    except sqlite3.Error as e:
        logger.error(f"Database setup error: {e}")
    finally:
        conn.close()

# Allowlist functions
def add_to_allowlist(user_id, approved_by=None, status="pending", answers=None):
    """Add a user to the allowlist"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().astimezone().isoformat()
        cursor.execute(
            "INSERT OR REPLACE INTO allowlist (user_id, approved_by, approved_at, status, answers) VALUES (?, ?, ?, ?, ?)",
            (user_id, approved_by, now if approved_by else None, status, answers)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error adding user to allowlist: {e}")
        return False
    finally:
        conn.close()

def remove_from_allowlist(user_id):
    """Remove a user from the allowlist"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM allowlist WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Error removing user from allowlist: {e}")
        return False
    finally:
        conn.close()

def check_allowlist(user_id):
    """Check if a user is in the allowlist"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM allowlist WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result
    except sqlite3.Error as e:
        logger.error(f"Error checking allowlist: {e}")
        return None
    finally:
        conn.close()

def get_allowlist():
    """Get all users in the allowlist"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM allowlist")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error getting allowlist: {e}")
        return []
    finally:
        conn.close()

def update_allowlist_status(user_id, status, approved_by=None):
    """Update a user's allowlist status"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().astimezone().isoformat()
        cursor.execute(
            "UPDATE allowlist SET status = ?, approved_by = ?, approved_at = ? WHERE user_id = ?",
            (status, approved_by, now if approved_by else None, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Error updating allowlist status: {e}")
        return False
    finally:
        conn.close()

# Warning functions
def add_warning(user_id, moderator_id, reason):
    """Add a warning to a user"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().astimezone().isoformat()
        cursor.execute(
            "INSERT INTO warnings (user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, moderator_id, reason, now)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error adding warning: {e}")
        return None
    finally:
        conn.close()

def get_warnings(user_id, active_only=True):
    """Get warnings for a user"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        if active_only:
            cursor.execute("SELECT * FROM warnings WHERE user_id = ? AND active = TRUE ORDER BY timestamp DESC", (user_id,))
        else:
            cursor.execute("SELECT * FROM warnings WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error getting warnings: {e}")
        return []
    finally:
        conn.close()

def clear_warnings(user_id, moderator_id=None):
    """Clear warnings for a user"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE warnings SET active = FALSE WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount
    except sqlite3.Error as e:
        logger.error(f"Error clearing warnings: {e}")
        return 0
    finally:
        conn.close()

# Ban functions
def add_ban(user_id, moderator_id, reason, expires_at=None):
    """Add a ban for a user"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().astimezone().isoformat()
        cursor.execute(
            "INSERT INTO bans (user_id, moderator_id, reason, timestamp, expires_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, moderator_id, reason, now, expires_at)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error adding ban: {e}")
        return None
    finally:
        conn.close()

def remove_ban(user_id):
    """Remove a ban for a user"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE bans SET active = FALSE WHERE user_id = ? AND active = TRUE", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Error removing ban: {e}")
        return False
    finally:
        conn.close()

def get_active_ban(user_id):
    """Get active ban for a user if exists"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM bans WHERE user_id = ? AND active = TRUE ORDER BY timestamp DESC LIMIT 1", (user_id,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Error getting active ban: {e}")
        return None
    finally:
        conn.close()

def get_all_bans():
    """Get all active bans"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM bans WHERE active = TRUE")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error getting all bans: {e}")
        return []
    finally:
        conn.close()

# Suggestion functions
def add_suggestion(user_id, content, message_id, channel_id):
    """Add a suggestion"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().astimezone().isoformat()
        cursor.execute(
            "INSERT INTO suggestions (user_id, content, message_id, channel_id, timestamp) VALUES (?, ?, ?, ?, ?)",
            (user_id, content, message_id, channel_id, now)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error adding suggestion: {e}")
        return None
    finally:
        conn.close()

def update_suggestion_status(suggestion_id, status):
    """Update a suggestion's status"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE suggestions SET status = ? WHERE id = ?", (status, suggestion_id))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Error updating suggestion status: {e}")
        return False
    finally:
        conn.close()

def get_suggestion(suggestion_id):
    """Get a suggestion by ID"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Error getting suggestion: {e}")
        return None
    finally:
        conn.close()

def get_suggestion_by_message(message_id):
    """Get a suggestion by message ID"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM suggestions WHERE message_id = ?", (message_id,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Error getting suggestion by message: {e}")
        return None
    finally:
        conn.close()

# Temp channel functions
def add_temp_channel(channel_id, user_id, purpose):
    """Add a temporary channel"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().astimezone().isoformat()
        cursor.execute(
            "INSERT INTO temp_channels (channel_id, user_id, created_at, purpose) VALUES (?, ?, ?, ?)",
            (channel_id, user_id, now, purpose)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error adding temp channel: {e}")
        return False
    finally:
        conn.close()

def remove_temp_channel(channel_id):
    """Remove a temporary channel"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM temp_channels WHERE channel_id = ?", (channel_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Error removing temp channel: {e}")
        return False
    finally:
        conn.close()

def get_temp_channels():
    """Get all temporary channels"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM temp_channels")
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error getting temp channels: {e}")
        return []
    finally:
        conn.close()
