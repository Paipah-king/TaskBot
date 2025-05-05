import os
import sys
import atexit
import signal
import logging
import telebot
import requests  # For keep-alive pings
from dotenv import load_dotenv
import database
from flask import Flask
from threading import Thread, Event, Lock
import time
import socket
from werkzeug.serving import is_running_from_reloader  # Prevent duplicate threads

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
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
    os.getenv('BOT_TOKEN'),
    threaded=False,
    skip_pending=True
)

# Flask app for health check
app = Flask(__name__)

@app.route('/')
def health_check():
    return "OK"

# Background thread for bot polling
bot_thread = None
keep_alive_thread = None
stop_event = Event()  # Event to signal threads to stop
resource_lock = Lock()  # Lock for shared resource access

def start_bot_polling():
    """Start bot polling in a background thread."""
    try:
        logger.info("🤖 Starting bot polling in background thread")
        with resource_lock:  # Protect shared resources if needed
            bot.infinity_polling()
    except Exception as e:
        logger.critical(f"💥 Bot polling crashed: {str(e)[:200]}")
        raise

def keep_alive():
    """Active ping to prevent Render shutdown."""
    while True:
        try:
            if os.getenv('RENDER'):
                requests.get(f"https://{os.getenv('RENDER_EXTERNAL_URL')}/", timeout=10)
        except Exception as e:
            logger.warning(f"Keep-alive failed: {e}")
        time.sleep(240)  # Ping every 4 mins (under 5-min timeout)

# Graceful shutdown handler
def shutdown():
    logger.info("🚦 Shutting down gracefully...")
    stop_event.set()  # Signal threads to stop
    try:
        if bot_thread and bot_thread.is_alive():
            bot.stop_polling()
            bot_thread.join()
            logger.info("🛑 Stopped bot polling thread.")
        
        if keep_alive_thread and keep_alive_thread.is_alive():
            keep_alive_thread.join()
            logger.info("🛑 Stopped keep-alive thread.")
        
        # Close database connections
        database.close_all_connections()
        logger.info("✅ Closed all database connections.")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    finally:
        sys.exit(0)

atexit.register(shutdown)
signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

# Main execution block
if __name__ == '__main__':
    if is_running_from_reloader():  # Prevent duplicate threads in dev
        logger.warning("🔁 Detected Flask reloader - skipping thread spawn")
    else:
        # Start threads only in production
        Thread(target=start_bot_polling, daemon=True).start()
        Thread(target=keep_alive, daemon=True).start()
    
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))
