import os
import json
import time
import logging
import requests
import re
from typing import Dict, List, Optional, Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    CallbackContext
)

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '7139353619:AAFv1JuHS6rDZ7V52G9C_oiJXHztJtxjBo0')
DATA_FILE = 'telegram_users.json'
COOLDOWN_FILE = 'cooldown.json'

CONFIG = {
    'required_channels': ['@Yagami_xlight', '@movie_mmsb'],
    'admin_chat_id': '6468293575',
    'cooldown_time': 10,  # seconds
    'max_search_results': 10,
    'max_message_length': 4000
}

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Utility Functions
def is_member_of_channels(user_id: Union[int, str]) -> bool:
    for channel in CONFIG['required_channels']:
        try:
            member = context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except Exception as e:
            logger.error(f"Failed to check membership for {user_id} in {channel}: {e}")
            continue
    return True

def validate_youtube_url(url: str) -> bool:
    pattern = r'^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$'
    return re.match(pattern, url) is not None

def get_audio_info(youtube_url: str) -> Dict:
    api_url = f"https://zawandkhin.serv00.net/api/yt.php?url={requests.utils.quote(youtube_url)}"
    try:
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('success', False):
            return {'ok': False, 'error': data.get('error', 'Invalid API response')}
        
        return {
            'ok': True,
            'title': data.get('title', 'Unknown Title'),
            'thumbnail': data.get('image', ''),
            'download_url': data.get('download_url', '')
        }
    except Exception as e:
        logger.error(f"Audio Info Error: {str(e)}")
        return {'ok': False, 'error': str(e)}

def search_youtube(query: str) -> List[Dict]:
    api_url = f"https://zawmyo123.serv00.net/api/ytsearch.php?query={requests.utils.quote(query)}"
    try:
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Search Error: {str(e)}")
        return []

def check_cooldown(user_id: Union[int, str]) -> Union[int, bool]:
    try:
        if os.path.exists(COOLDOWN_FILE):
            with open(COOLDOWN_FILE, 'r') as f:
                cooldowns = json.load(f)
        else:
            return False
        
        current_time = time.time()
        user_id_str = str(user_id)
        
        if user_id_str in cooldowns:
            elapsed = current_time - cooldowns[user_id_str]
            if elapsed < CONFIG['cooldown_time']:
                return CONFIG['cooldown_time'] - int(elapsed)
        
        return False
    except Exception as e:
        logger.error(f"Cooldown Check Error: {str(e)}")
        return False

def set_cooldown(user_id: Union[int, str]) -> None:
    try:
        cooldowns = {}
        if os.path.exists(COOLDOWN_FILE):
            with open(COOLDOWN_FILE, 'r') as f:
                cooldowns = json.load(f)
        
        cooldowns[str(user_id)] = time.time()
        
        with open(COOLDOWN_FILE, 'w') as f:
            json.dump(cooldowns, f)
    except Exception as e:
        logger.error(f"Cooldown Set Error: {str(e)}")

# Bot Handlers
def start(update: Update, context: CallbackContext) -> None:
    if not is_member_of_channels(update.effective_user.id):
        update.message.reply_text(
            "🚫 Access Denied\n\nYou need to join our channels to use this bot:\n\n" +
            "\n".join(f"{i+1}. {channel}" for i, channel in enumerate(CONFIG['required_channels'])) +
            "\n\nJoin them and click the button below to verify:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Verify Membership", callback_data='check_membership')]
            ])
        )
        return
    
    update.message.reply_text(
        "🎵 <b>YouTube Music Bot</b>\n\n"
        "Send me:\n"
        "• A song name to search\n"
        "• A YouTube URL to download\n\n"
        "<i>Made by @ItachiXCoder</i>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url="https://t.me/Yagami_xlight")]
        ])
    )

def handle_message(update: Update, context: CallbackContext) -> None:
    if not is_member_of_channels(update.effective_user.id):
        update.message.reply_text(
            "🚫 Access Denied\n\nYou need to join our channels to use this bot:\n\n" +
            "\n".join(f"{i+1}. {channel}" for i, channel in enumerate(CONFIG['required_channels'])) +
            "\n\nJoin them and click the button below to verify:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Verify Membership", callback_data='check_membership')]
            ])
        )
        return
    
    text = update.message.text.strip()
    
    if text.startswith('/admin') and str(update.effective_user.id) == CONFIG['admin_chat_id']:
        update.message.reply_text("Admin panel coming soon...")
    elif validate_youtube_url(text):
        handle_youtube_url(update, context, text)
    else:
        handle_search(update, context, text)

def handle_youtube_url(update: Update, context: CallbackContext, url: str) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if remaining := check_cooldown(user_id):
        update.message.reply_text(f"⏳ Please wait {remaining} seconds before your next request")
        return
    
    set_cooldown(user_id)
    message = update.message.reply_text("⏳ Processing your YouTube link...")
    
    audio_info = get_audio_info(url)
    if not audio_info.get('ok'):
        message.edit_text(
            f"❌ Failed to process this YouTube URL\n\nError: {audio_info.get('error', 'Unknown error')}"
        )
        return
    
    message.edit_text(
        f"🎵 <b>{audio_info['title']}</b>\n\n"
        f"🔗 <a href=\"{audio_info['download_url']}\">Download Audio</a>\n\n"
        "<i>Powered by @ItachiXCoder</i>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url="https://t.me/Yagami_xlight")]
        ])
    )

def handle_search(update: Update, context: CallbackContext, query: str) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if remaining := check_cooldown(user_id):
        update.message.reply_text(f"⏳ Please wait {remaining} seconds before your next request")
        return
    
    set_cooldown(user_id)
    message = update.message.reply_text(f"🔍 Searching YouTube for \"{query}\"...")
    
    results = search_youtube(query)
    if not results:
        message.edit_text(f"❌ No results found for \"{query}\"")
        return
    
    message_text = "📋 <b>Search Results:</b>\n\n"
    keyboard = []
    
    for i, video in enumerate(results[:CONFIG['max_search_results']]):
        num = i + 1
        message_text += f"{num}. <b>{video.get('title', 'No title')}</b>\n"
        keyboard.append([
            InlineKeyboardButton(f"{num}. Download", callback_data=f"download|{video.get('url', '')}")
        ])
    
    message.edit_text(
        message_text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def handle_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    data = query.data
    
    if not is_member_of_channels(user_id):
        query.edit_message_text(
            "🚫 Access Denied\n\nYou need to join our channels to use this bot:\n\n" +
            "\n".join(f"{i+1}. {channel}" for i, channel in enumerate(CONFIG['required_channels'])) +
            "\n\nJoin them and click the button below to verify:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Verify Membership", callback_data='check_membership')]
            ])
        )
        return
    
    data_parts = data.split('|')
    action = data_parts[0]
    param = data_parts[1] if len(data_parts) > 1 else None
    
    if action == 'check_membership':
        if is_member_of_channels(user_id):
            query.edit_message_text(
                "✅ Membership Verified!\n\nYou can now use all bot features.\n\n"
                "Send /start to begin."
            )
        else:
            query.answer("❌ You still need to join all channels!", show_alert=True)
    
    elif action == 'download' and param:
        if remaining := check_cooldown(user_id):
            query.answer(f"⏳ Please wait {remaining} seconds before your next request", show_alert=True)
            return
        
        set_cooldown(user_id)
        query.edit_message_text("⏳ Processing your request...")
        
        audio_info = get_audio_info(param)
        if not audio_info.get('ok'):
            query.edit_message_text(
                "❌ Failed to process this video\n\n"
                f"Error: {audio_info.get('error', 'Unknown error')}\n\n"
                "Try again or contact support."
            )
            return
        
        query.edit_message_text(
            f"🎵 <b>{audio_info['title']}</b>\n\n"
            f"🔗 <a href=\"{audio_info['download_url']}\">Download Audio</a>\n\n"
            "<i>Powered by @ItachiXCoder</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url="https://t.me/Yagami_xlight")]
            ])
        )

def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(f"Update {update} caused error {context.error}")

def main() -> None:
    # Create the Updater and pass it your bot's token.
    updater = Updater(BOT_TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Register handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dispatcher.add_handler(CallbackQueryHandler(handle_callback))
    dispatcher.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == '__main__':
    main()
