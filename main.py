import os
import sys
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

# PORT LOCK - prevents multiple instances
lock_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    lock_socket.bind(('localhost', 47200))  # Unique port
    logger.info("🔒 Acquired instance lock")
except socket.error:
    logger.error("🛑 Another bot instance is running")
    sys.exit(1)

# Flask health check setup
app = Flask(__name__)

@app.route('/')
def home():
    return "OK"

# Initialize bot with your token from .env
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))

# Critical fixes
bot.skip_pending = True  # Ignore old messages
bot.delete_webhook()     # Clear previous connections
logger.info("🔄 Telegram API connection reset")

# Main execution block
if __name__ == '__main__':
    # Start Flask in background
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 10000}, daemon=True).start()

    # Start bot
    try:
        logger.info("🤖 Bot running successfully")
        bot.infinity_polling()
    except Exception as e:
        logger.critical(f"💥 Fatal error: {str(e)[:200]}")
        raise
