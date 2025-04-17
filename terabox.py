from aria2p import API as Aria2API, Client as Aria2Client
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import logging
import math
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, MessageDeleteForbidden
from pymongo import MongoClient
import time
import threading
import uuid
import urllib.parse
from urllib.parse import urlparse
import requests

load_dotenv('config.env', override=True)
logging.basicConfig(
    level=logging.INFO,  
    format="[%(asctime)s - %(name)s - %(levelname)s] %(message)s - %(filename)s:%(lineno)d"
)

logger = logging.getLogger(__name__)

logging.getLogger("pyrogram.session").setLevel(logging.ERROR)
logging.getLogger("pyrogram.connection").setLevel(logging.ERROR)
logging.getLogger("pyrogram.dispatcher").setLevel(logging.ERROR)

aria2 = Aria2API(
    Aria2Client(
        host="http://localhost",
        port=6800,
        secret=""
    )
)
options = {
    "max-tries": "50",
    "retry-wait": "3",
    "continue": "true",
    "allow-overwrite": "true",
    "min-split-size": "4M",
    "split": "10"
}

aria2.set_global_options(options)

API_ID = os.environ.get('TELEGRAM_API', '')
if len(API_ID) == 0:
    logging.error("TELEGRAM_API variable is missing! Exiting now")
    exit(1)

API_HASH = os.environ.get('TELEGRAM_HASH', '')
if len(API_HASH) == 0:
    logging.error("TELEGRAM_HASH variable is missing! Exiting now")
    exit(1)
    
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
if len(BOT_TOKEN) == 0:
    logging.error("BOT_TOKEN variable is missing! Exiting now")
    exit(1)

DUMP_CHAT_ID = os.environ.get('DUMP_CHAT_ID', '')
if len(DUMP_CHAT_ID) == 0:
    logging.error("DUMP_CHAT_ID variable is missing! Exiting now")
    exit(1)
else:
    DUMP_CHAT_ID = int(DUMP_CHAT_ID)

FSUB_ID = os.environ.get('FSUB_ID', '')
if len(FSUB_ID) == 0:
    logging.error("FSUB_ID variable is missing! Exiting now")
    exit(1)
else:
    FSUB_ID = int(FSUB_ID)

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if len(DATABASE_URL) == 0:
    logging.error("DATABASE_URL variable is missing! Exiting now")
    exit(1)

SHORTENER_API = os.environ.get('SHORTENER_API', None)  # Made optional

USER_SESSION_STRING = os.environ.get('USER_SESSION_STRING', '')
if len(USER_SESSION_STRING) == 0:
    logging.info("USER_SESSION_STRING variable is missing! Bot will split Files in 2Gb...")
    USER_SESSION_STRING = None

DATABASE_NAME = "terabox"
COLLECTION_NAME = "user_requests"

client = MongoClient(DATABASE_URL)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

app = Client("jetbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user = None
SPLIT_SIZE = 2093796556
if USER_SESSION_STRING:
    user = Client("jetu", api_id=API_ID, api_hash=API_HASH, session_string=USER_SESSION_STRING)
    SPLIT_SIZE = 4241280205

VALID_DOMAINS = [
    'terabox.com', 'nephobox.com', '4funbox.com', 'mirrobox.com', 
    'momerybox.com', 'teraboxapp.com', '1024tera.com', 
    'terabox.app', 'gibibox.com', 'goaibox.com', 'terasharelink.com', 
    'teraboxlink.com', 'terafileshare.com'
]
last_update_time = 0

async def is_user_member(client, user_id):
    try:
        member = await client.get_chat_member(FSUB_ID, user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return True
        else:
            return False
    except Exception as e:
        logging.error(f"Error checking membership status for user {user_id}: {e}")
        return False
    
def is_valid_url(url):
    parsed_url = urlparse(url)
    return any(parsed_url.netloc.endswith(domain) for domain in VALID_DOMAINS)

def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"

def shorten_url(url):
    if not SHORTENER_API:
        return url  # Return original URL if no shortener API is configured
    
    api_url = "https://api.modijiurl.com/api"
    params = {
        "api": SHORTENER_API,
        "url": url
    }
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success":
            return data.get("shortenedUrl")
        else:
            logger.error(f"Failed to shorten URL: {data}")
            return url  # Fallback to original URL
    except Exception as e:
        logger.error(f"Error shortening URL: {e}")
        return url  # Fallback to original URL

def generate_uuid(user_id):
    token = str(uuid.uuid4())
    collection.update_one(
        {"user_id": user_id},
        {"$set": {"token": token, "token_status": "inactive", "token_expiry": None}},
        upsert=True
    )
    return token

def activate_token(user_id, token):
    user_data = collection.find_one({"user_id": user_id, "token": token})
    if user_data:
        collection.update_one(
            {"user_id": user_id, "token": token},
            {"$set": {"token_status": "active", "token_expiry": datetime.now() + timedelta(hours=12)}}
        )
        return True
    return False

def has_valid_token(user_id):
    user_data = collection.find_one({"user_id": user_id})
    if user_data and user_data.get("token_status") == "active":
        if datetime.now() < user_data.get("token_expiry"):
            return True
    return False

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    join_button = InlineKeyboardButton("ᴊᴏɪɴ ❤️🚀", url="https://t.me/jetmirror")
    developer_button = InlineKeyboardButton("ᴅᴇᴠᴇʟᴏᴘᴇʀ ⚡️", url="https://t.me/rtx5069")
    repo69 = InlineKeyboardButton("ʀᴇᴘᴏ 🌐", url="https://github.com/Hrishi2861/Terabox-Downloader-Bot")
    reply_markup = InlineKeyboardMarkup([[join_button, developer_button], [repo69]])
    final_msg = "🌟 ɪ ᴀᴍ ᴀ ᴛᴇʀᴀʙᴏx ᴅᴏᴡɴʟᴏᴀᴅᴇʀ ʙᴏᴛ.\n\nYou already have a valid token!"
    video_file_id = "/app/Jet-Mirror.mp4"
    
    if len(message.command) > 1 and len(message.command[1]) == 36:
        token = message.command[1]
        user_id = message.from_user.id

        if activate_token(user_id, token):
            if os.path.exists(video_file_id):
                await client.send_video(
                    chat_id=message.chat.id,
                    video=video_file_id,
                    caption="🌟 ɪ ᴀᴍ ᴀ ᴛᴇʀᴀʙᴏx ᴅᴏᴡɴʟᴏᴀᴅᴇʀ ʙᴏᴛ.\n\nYour token has been activated successfully! You can now use the bot.",
                    reply_markup=reply_markup
                    )
            else:
                await message.reply_text("🌟 ɪ ᴀᴍ ᴀ ᴛᴇʀᴀʙᴏx ᴅᴏᴡɴʟᴏᴀᴅᴇʀ ʙᴏᴛ.\n\nYour token has been activated successfully! You can now use the bot.", reply_markup=reply_markup)
        else:
            if os.path.exists(video_file_id):
                await client.send_video(
                    chat_id=message.chat.id,
                    video=video_file_id,
                    caption="🌟 ɪ ᴀᴍ ᴀ ᴛᴇʀᴀʙᴏx ᴅᴏᴡɴʟᴏᴀᴅᴇʀ ʙᴏᴛ.\n\nInvalid token. Please generate a new one using /start.",
                    reply_markup=reply_markup
                    )
            else:
                await message.reply_text("🌟 ɪ ᴀᴍ ᴀ ᴛᴇʀᴀʙᴏx ᴅᴏᴡɴʟᴏᴀᴅᴇʀ ʙᴏᴛ.\n\nInvalid token. Please generate a new one using /start.", reply_markup=reply_markup)
    else:
        user_id = message.from_user.id
        if not has_valid_token(user_id):
            token = generate_uuid(user_id)
            long_url = f"https://redirect.jet-mirror.in/{app.me.username}/{token}"
            short_url = shorten_url(long_url)
            
            if SHORTENER_API:
                reply_markup2 = InlineKeyboardMarkup([[InlineKeyboardButton("Generate Token Link", url=short_url)], [join_button, developer_button], [repo69]])
            else:
                reply_markup2 = InlineKeyboardMarkup([[InlineKeyboardButton("Generate Token Link", url=long_url)], [join_button, developer_button], [repo69]])
                
            if os.path.exists(video_file_id):
                await client.send_video(
                chat_id=message.chat.id,
                video=video_file_id,
                caption="🌟 ɪ ᴀᴍ ᴀ ᴛᴇʀᴀʙᴏx ᴅᴏᴡɴʟᴏᴀᴅᴇʀ ʙᴏᴛ.\n\nPlease generate your Token, which will be valid for 12Hrs.",
                reply_markup=reply_markup2
                )
            else:
                await message.reply_text(
                "🌟 ɪ ᴀᴍ ᴀ ᴛᴇʀᴀʙᴏx ᴅᴏᴡɴʟᴏᴀᴅᴇʀ ʙᴏᴛ.\n\n"
                "Please generate your Token, which will be valid for 12Hrs.",
                reply_markup=reply_markup2
            )
        else:
            if os.path.exists(video_file_id):
                await client.send_video(
                    chat_id=message.chat.id,
                    video=video_file_id,
                    caption=final_msg,
                    reply_markup=reply_markup
                    )
            else:
                await message.reply_text(final_msg, reply_markup=reply_markup)

# [Rest of the code remains the same...]

async def start_user_client():
    if user:
        await user.start()
        logger.info("User client started.")

def run_user():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_user_client())

if __name__ == "__main__":
    if user:
        logger.info("Starting both bot and user clients...")
        user_thread = threading.Thread(target=run_user)
        user_thread.start()

    logger.info("Starting bot client...")
    logger.info("Bot client Started...")
    app.run()
