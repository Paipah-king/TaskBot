import os
import sys
import atexit
import signal
import socket
import logging
from threading import Thread
from flask import Flask
import telebot
from dotenv import load_dotenv

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

# Flask health check setup
flask_app = Flask(__name__)
PORT = 10000  # Starting port

def find_available_port():
    """Find open port starting from PORT"""
    global PORT
    with socket.socket() as s:
        while PORT < 10100:
            try:
                s.bind(('0.0.0.0', PORT))
                return PORT
            except OSError:
                PORT += 1
        raise RuntimeError("No available ports")

@flask_app.route('/')
def health_check():
    return "🟢 Bot Operational", 200

# Graceful shutdown logic
def graceful_shutdown(signum=None, frame=None):
    """Handle all shutdown scenarios"""
    logger.info(f"Shutting down ({'SIGTERM' if signum == signal.SIGTERM else 'SIGINT' if signum else 'manual'})")
    try:
        if hasattr(bot, 'stop_polling'):
            bot.stop_polling()
            logger.info("Stopped bot polling.")
        logger.info("✅ Resources released")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    finally:
        sys.exit(0)

# Initialize bot with your token from .env
bot = telebot.TeleBot(
    os.getenv('BOT_TOKEN'),  # Keep .env loading
    threaded=False,
    skip_pending=True,
    num_threads=1
)

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

# Main execution block
if __name__ == '__main__':
    # Register shutdown handlers
    atexit.register(graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)

    # Start Flask in background
    flask_port = find_available_port()
    Thread(
        target=flask_app.run,
        kwargs={'host': '0.0.0.0', 'port': flask_port},
        daemon=True
    ).start()

    # Start bot with crash protection
    try:
        logger.info(f"🚀 Starting bot (PID: {os.getpid()})")
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"💥 Fatal error: {str(e)[:200]}")
        graceful_shutdown()
