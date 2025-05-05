import os
import sys
import fcntl 
import atexit
import signal
import socket
import logging
import time
from threading import Thread
from flask import Flask
import telebot
from dotenv import load_dotenv

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

# Instance lock to prevent multiple instances
class InstanceLock:
    def __enter__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(('0.0.0.0', 47200))  # Unique port for lock
            logging.info("🔒 Acquired instance lock")
        except socket.error:
            logging.error("🛑 Another instance is running")
            sys.exit(1)
        return self

    def __exit__(self, *args):
        self.sock.close()
        logging.info("🔓 Released instance lock")

# Telegram API cleanup
def reset_telegram_connection(bot):
    """Ensure clean API connection"""
    try:
        bot.delete_webhook()  # Clear any existing webhook
        time.sleep(1)
        logging.info("🔄 Telegram API connection reset")
    except Exception as e:
        logging.warning(f"⚠️ API reset failed: {str(e)[:100]}")

# Initialize bot with your token from .env
bot = telebot.TeleBot(
    os.getenv('BOT_TOKEN'),
    threaded=False,          # Critical for Render
    skip_pending=True,       # Avoid message pileup
    num_threads=1            # Enforce single thread
)

# Flask health check setup
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "OK"

def find_available_port(start_port=10000):
    """Find open port starting from start_port"""
    port = start_port
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('0.0.0.0', port))
            sock.close()
            return port
        except OSError:
            port += 1

# Graceful shutdown logic
def shutdown_handler(signum=None, frame=None):
    logging.info(f"🚦 Received {'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'}")
    try:
        if hasattr(bot, 'stop_polling'):
            bot.stop_polling()
    finally:
        sys.exit(0)

# Main execution block
if __name__ == '__main__':
    # Register shutdown handlers
    atexit.register(shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    # Instance lock + API cleanup
    with InstanceLock():
        reset_telegram_connection(bot)

        # Start Flask health check
        flask_port = find_available_port()
        Thread(
            target=flask_app.run,
            kwargs={'host': '0.0.0.0', 'port': flask_port},
            daemon=True
        ).start()

        # Start bot with crash protection
        try:
            logging.info("🤖 Bot started successfully")
            bot.infinity_polling()
        except Exception as e:
            logging.critical(f"💥 Fatal error: {str(e)[:200]}")
            raise
