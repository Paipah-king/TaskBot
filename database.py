import sqlite3
import time
import logging
import threading

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# SQLite connection setup
def get_connection():
    try:
        conn = sqlite3.connect('bot_data.db', check_same_thread=False)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise

# Initialize database and tables
def initialize_database():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS verified_users (
                            user_id INTEGER, 
                            group_id INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
                            task_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                            description TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS task_completions (
                            task_id INTEGER, 
                            user_id INTEGER)''')
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Error initializing database: {e}")
        raise

# Retry decorator for database operations
def retry_db_operation(func):
    def wrapper(*args, **kwargs):
        retries = 3
        delay = 2  # seconds
        for attempt in range(retries):
            try:
                return func(*args, **kwargs)
            except sqlite3.Error as e:
                logger.warning(f"Database operation failed (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    logger.error(f"Database operation failed after {retries} attempts.")
                    raise
    return wrapper

# Add a verified user
@retry_db_operation
def add_verified_user(user_id, group_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO verified_users (user_id, group_id) VALUES (?, ?)', (user_id, group_id))
    conn.commit()
    conn.close()

# Check if a user is verified
@retry_db_operation
def is_verified(user_id, group_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM verified_users WHERE user_id=? AND group_id=?', (user_id, group_id))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# Dictionary to store timers and events for each user
user_timers = {}

# Start auto-kick timer
def kick_unverified(chat_id, user_id, timeout):
    if user_id in user_timers:
        user_timers[user_id]['event'].set()
        user_timers.pop(user_id, None)

    cancel_event = threading.Event()
    timer = threading.Thread(target=check_and_kick, args=(chat_id, user_id, cancel_event, timeout))
    user_timers[user_id] = {'timer': timer, 'event': cancel_event}
    timer.start()

def check_and_kick(chat_id, user_id, cancel_event, timeout):
    if not cancel_event.wait(timeout):
        return chat_id, user_id
    user_timers.pop(user_id, None)

# Cancel all active timers
def cancel_all_timers():
    for user_id, timer_data in user_timers.items():
        timer_data['event'].set()
    user_timers.clear()

# Initialize the database when the module is imported
initialize_database()

# Required dependencies should be listed in a requirements.txt file, not in the Python script.