import logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import database
from dotenv import load_dotenv
import os
import signal
import sys
from flask import Flask
import socket
from threading import Lock
import atexit
from time import sleep

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

# Load environment variables from .env file
load_dotenv()

# Initialize bot with your token from .env
bot = telebot.TeleBot(
    os.getenv('BOT_TOKEN'),  # Keeps current .env loading
    threaded=False,          # Disables internal threading
    skip_pending=True,       # Ignores queued messages
    num_threads=1            # Explicit single thread
)

# Maintenance mode flag
maintenance_mode = False

# Graceful shutdown logic
def graceful_shutdown(signum=None, frame=None):
    """Emergency cleanup with logging"""
    print("🛑 Received shutdown signal" + (" SIGTERM" if signum == signal.SIGTERM else 
                                           " SIGINT" if signum == signal.SIGINT else ""))
    logger.info("Shutting down bot gracefully...")
    try:
        if hasattr(bot, 'stop_polling'):
            bot.stop_polling()
            logger.info("Stopped bot polling.")
        database.cancel_all_timers()
        logger.info("Canceled all timers.")
        # Add additional cleanup logic here if needed
        logger.info("✅ Resources released")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    finally:
        sys.exit(0 if signum else 1)  # Clean exit for signals

# Register shutdown handlers
atexit.register(graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)  # Render termination
signal.signal(signal.SIGINT, graceful_shutdown)   # Ctrl+C

# Flask web server to satisfy Render's port requirement
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

# Start Flask in a separate thread
threading.Thread(
    target=app.run,
    kwargs={'host': '0.0.0.0', 'port': 10000},
    daemon=True
).start()

# Check if user is admin
def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

# Greet new members
@bot.message_handler(content_types=['new_chat_members'])
def greet_new_member(message):
    if maintenance_mode:
        bot.send_message(message.chat.id, "The bot is currently in maintenance mode. Please try again later.")
        return
    for user in message.new_chat_members:
        bot.send_message(
            message.chat.id,
            f"Hi {user.first_name}! Please verify by sending 'I am here'."
        )
        database.kick_unverified(message.chat.id, user.id, timeout=300)

# Process unverified user kick
def process_kick(chat_id, user_id):
    try:
        bot.kick_chat_member(chat_id, user_id)
        bot.send_message(chat_id, f"User ID {user_id} was removed for not verifying.")
        logger.info(f"Kicked user {user_id} from chat {chat_id}.")
    except Exception as e:
        logger.error(f"Failed to kick user {user_id} from chat {chat_id}: {e}")

# Verify users
@bot.message_handler(regexp='I am here')
def verify_user(message):
    if maintenance_mode:
        bot.reply_to(message, "The bot is currently in maintenance mode. Please try again later.")
        return
    user_id = message.from_user.id
    group_id = message.chat.id
    try:
        if not database.is_verified(user_id, group_id):
            database.add_verified_user(user_id, group_id)
            bot.reply_to(message, "✅ You are now verified!")
        else:
            bot.reply_to(message, "You're already verified.")
    except Exception as e:
        logger.error(f"Error verifying user: {e}")
        bot.reply_to(message, "An error occurred while verifying you. Please try again.")

# Handle task completion
@bot.callback_query_handler(func=lambda call: call.data.startswith('complete_'))
def complete_task(call):
    if maintenance_mode:
        bot.answer_callback_query(call.id, "The bot is currently in maintenance mode. Please try again later.")
        return
    user_id = call.from_user.id
    if not database.is_verified(user_id, call.message.chat.id):
        bot.answer_callback_query(call.id, "Verify first with 'I am here'.")
        return
    task_id = int(call.data.split('_')[1])
    try:
        completions = database.get_task_completions(task_id)
        if any(user_id == completion[0] for completion in completions):
            bot.answer_callback_query(call.id, "You have already completed this task.")
            return
        database.add_task_completion(task_id, user_id)
        bot.answer_callback_query(call.id, "Task completed!")
    except Exception as e:
        logger.error(f"Error completing task: {e}")
        bot.answer_callback_query(call.id, "An error occurred while completing the task. Please try again.")

# Start bot with protected execution block
if __name__ == "__main__":
    try:
        print(f"🚀 Starting bot instance (PID: {os.getpid()})")
        bot.infinity_polling(
            restart_on_change=True,  # Auto-recover from API errors
            timeout=20               # Faster reconnect
        )
    except Exception as e:
        print(f"💥 Crash detected: {str(e)[:100]}...")
        graceful_shutdown()
    finally:
        print("🔁 Attempting self-recovery...")
        sleep(5)
        os.execv(sys.executable, ['python'] + sys.argv)  # Auto-restart
