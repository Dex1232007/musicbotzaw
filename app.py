import os
import json
import time
import logging
import re
from functools import wraps
from typing import Dict, List, Optional, Tuple, Union

import requests
from flask import Flask, request, jsonify, Response

# Configuration
class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN', '7139353619:AAFv1JuHS6rDZ7V52G9C_oiJXHztJtxjBo0')
    API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}/'
    DATA_FILE = 'data/telegram_users.json'
    COOLDOWN_FILE = 'data/cooldown.json'
    LOG_FILE = 'logs/bot.log'
    
    REQUIRED_CHANNELS = ['@Yagami_xlight', '@movie_mmsb']
    ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID', '6468293575')
    COOLDOWN_TIME = 10  # seconds
    MAX_SEARCH_RESULTS = 10
    MAX_MESSAGE_LENGTH = 4000

    @classmethod
    def ensure_directories_exist(cls):
        os.makedirs('data', exist_ok=True)
        os.makedirs('logs', exist_ok=True)

# Initialize configuration
Config.ensure_directories_exist()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Utility Decorators
def cooldown_check(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user_id = kwargs.get('user_id')
        if remaining := check_cooldown(user_id):
            return {'ok': False, 'error': f'Please wait {remaining} seconds before your next request'}
        return func(*args, **kwargs)
    return wrapper

def channel_membership_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user_id = kwargs.get('user_id')
        if not is_member_of_channels(user_id):
            return {
                'ok': False,
                'error': 'Channel membership required',
                'message': "🚫 Access Denied\n\nYou need to join our channels to use this bot:\n\n" +
                          "\n".join(f"{i+1}. {channel}" for i, channel in enumerate(Config.REQUIRED_CHANNELS)) +
                          "\n\nJoin them and click the button below to verify:",
                'keyboard': [[{'text': "✅ Verify Membership", 'callback_data': 'check_membership'}]]
            }
        return func(*args, **kwargs)
    return wrapper

# Core Functions
def api_request(method: str, params: Optional[Dict] = None) -> Optional[Dict]:
    url = f"{Config.API_URL}{method}"
    try:
        response = requests.post(
            url,
            json=params,
            timeout=(5, 30)  # 5 seconds connect timeout, 30 seconds read timeout
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API Request Error ({method}): {str(e)}")
        return None

def send_message(
    chat_id: Union[int, str],
    text: str,
    keyboard: Optional[List] = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True
) -> Optional[Dict]:
    params = {
        'chat_id': chat_id,
        'text': text[:Config.MAX_MESSAGE_LENGTH],
        'parse_mode': parse_mode,
        'disable_web_page_preview': disable_web_page_preview
    }
    
    if keyboard:
        params['reply_markup'] = {'inline_keyboard': keyboard}
    
    return api_request('sendMessage', params)

def edit_message(
    chat_id: Union[int, str],
    message_id: int,
    text: str,
    keyboard: Optional[List] = None
) -> Optional[Dict]:
    params = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text[:Config.MAX_MESSAGE_LENGTH],
        'parse_mode': 'HTML'
    }
    
    if keyboard:
        params['reply_markup'] = {'inline_keyboard': keyboard}
    
    return api_request('editMessageText', params)

def answer_callback(callback_id: str, text: str, show_alert: bool = False) -> Optional[Dict]:
    return api_request('answerCallbackQuery', {
        'callback_query_id': callback_id,
        'text': text,
        'show_alert': show_alert
    })

def send_chat_action(chat_id: Union[int, str], action: str) -> Optional[Dict]:
    return api_request('sendChatAction', {
        'chat_id': chat_id,
        'action': action
    })

def send_audio_stream(chat_id: Union[int, str], audio_url: str) -> Optional[Dict]:
    send_chat_action(chat_id, 'upload_audio')
    
    try:
        keyboard = [
            [{'text': "💐 Join Our Channel", 'url': "https://t.me/Yagami_xlight"}]
        ]
        
        with requests.get(audio_url, stream=True, timeout=30) as audio_stream:
            audio_stream.raise_for_status()
            
            files = {
                'audio': ('audio.mp3', audio_stream.raw, 'audio/mpeg'),
                'chat_id': (None, str(chat_id)),
                'caption': (None, 'Made by @ItachiXCoder'),
                'reply_markup': (None, json.dumps({'inline_keyboard': keyboard}))
            }
            
            response = requests.post(
                f"{Config.API_URL}sendAudio",
                files=files,
                timeout=60
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Audio Stream Error: {str(e)}")
        send_message(chat_id, "Failed to process the audio file.")
        return None

def is_member_of_channels(user_id: Union[int, str]) -> bool:
    for channel in Config.REQUIRED_CHANNELS:
        response = api_request('getChatMember', {
            'chat_id': channel,
            'user_id': user_id
        })
        
        if not response or not response.get('result', {}).get('status'):
            logger.error(f"Failed to check membership for {user_id} in {channel}")
            continue
        
        status = response['result']['status']
        if status not in ['member', 'administrator', 'creator']:
            return False
    
    return True

def validate_youtube_url(url: str) -> bool:
    pattern = r'^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$'
    return re.match(pattern, url) is not None

@cooldown_check
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
            'duration': data.get('duration', ''),
            'download_url': data.get('download_url', '')
        }
    except Exception as e:
        logger.error(f"Audio Info Error: {str(e)}")
        return {'ok': False, 'error': str(e)}

@cooldown_check
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
        if os.path.exists(Config.COOLDOWN_FILE):
            with open(Config.COOLDOWN_FILE, 'r') as f:
                cooldowns = json.load(f)
        else:
            return False
        
        current_time = time.time()
        user_id_str = str(user_id)
        
        if user_id_str in cooldowns:
            elapsed = current_time - cooldowns[user_id_str]
            if elapsed < Config.COOLDOWN_TIME:
                return Config.COOLDOWN_TIME - int(elapsed)
        
        return False
    except Exception as e:
        logger.error(f"Cooldown Check Error: {str(e)}")
        return False

def set_cooldown(user_id: Union[int, str]) -> None:
    try:
        cooldowns = {}
        if os.path.exists(Config.COOLDOWN_FILE):
            with open(Config.COOLDOWN_FILE, 'r') as f:
                cooldowns = json.load(f)
        
        cooldowns[str(user_id)] = time.time()
        
        with open(Config.COOLDOWN_FILE, 'w') as f:
            json.dump(cooldowns, f, indent=2)
    except Exception as e:
        logger.error(f"Cooldown Set Error: {str(e)}")

# Handlers
def handle_start(chat_id: Union[int, str]) -> None:
    send_message(
        chat_id,
        "🎵 <b>YouTube Music Bot</b>\n\n"
        "Send me:\n"
        "• A song name to search\n"
        "• A YouTube URL to download\n\n"
        "<i>Made by @ItachiXCoder</i>",
        [
            [{'text': "🎛️ Mini App", 'web_app': {'url': 'https://itachi.x10.mx'}}],
            [{'text': "📢 Join Channel", 'url': "https://t.me/Yagami_xlight"}]
        ]
    )

def handle_youtube_url(chat_id: Union[int, str], user_id: Union[int, str], url: str) -> None:
    set_cooldown(user_id)
    msg = send_message(chat_id, "⏳ Processing your YouTube link...")
    
    audio_info = get_audio_info(url)
    if not audio_info.get('ok'):
        edit_message(
            chat_id,
            msg['result']['message_id'],
            f"❌ Failed to process this YouTube URL\n\nError: {audio_info.get('error', 'Unknown error')}"
        )
        return
    
    edit_message(
        chat_id,
        msg['result']['message_id'],
        f"🎵 <b>{audio_info['title']}</b>\n\n"
        f"⏳ Downloading audio...",
        [
            [{'text': "📢 Join Channel", 'url': "https://t.me/Yagami_xlight"}]
        ]
    )
    
    audio_response = send_audio_stream(chat_id, audio_info['download_url'])
    if not audio_response or not audio_response.get('ok'):
        edit_message(
            chat_id,
            msg['result']['message_id'],
            f"🎵 <b>{audio_info['title']}</b>\n\n"
            f"🔗 <a href=\"{audio_info['download_url']}\">Download Audio</a>\n\n"
            "<i>Failed to send as audio file. Use the download link instead.</i>",
            [
                [{'text': "📢 Join Channel", 'url': "https://t.me/Yagami_xlight"}]
            ]
        )

def handle_search(chat_id: Union[int, str], user_id: Union[int, str], query: str) -> None:
    set_cooldown(user_id)
    msg = send_message(chat_id, f"🔍 Searching YouTube for \"{query}\"...")
    
    results = search_youtube(query)
    if not results:
        edit_message(
            chat_id,
            msg['result']['message_id'],
            f"❌ No results found for \"{query}\""
        )
        return
    
    message_text = "📋 <b>Search Results:</b>\n\n"
    keyboard = []
    
    for i, video in enumerate(results[:Config.MAX_SEARCH_RESULTS]):
        num = i + 1
        message_text += f"{num}. <b>{video.get('title', 'No title')}</b>\n"
        keyboard.append([
            {'text': f"{num}. Download", 'callback_data': f"download|{video.get('url', '')}"}
        ])
    
    edit_message(
        chat_id,
        msg['result']['message_id'],
        message_text,
        keyboard
    )

def handle_callback(
    callback_id: str,
    chat_id: Union[int, str],
    user_id: Union[int, str],
    message_id: int,
    data: str
) -> None:
    data_parts = data.split('|')
    action = data_parts[0]
    param = data_parts[1] if len(data_parts) > 1 else None
    
    if action == 'check_membership':
        if is_member_of_channels(user_id):
            edit_message(
                chat_id,
                message_id,
                "✅ Membership Verified!\n\nYou can now use all bot features.\n\n"
                "Send /start to begin."
            )
            answer_callback(callback_id, "Membership verified successfully!")
        else:
            answer_callback(callback_id, "❌ You still need to join all channels!", True)
    
    elif action == 'download' and param:
        set_cooldown(user_id)
        answer_callback(callback_id, "Processing your request...")
        edit_message(chat_id, message_id, "⏳ Processing your request...")
        
        audio_info = get_audio_info(param)
        if not audio_info.get('ok'):
            edit_message(
                chat_id,
                message_id,
                "❌ Failed to process this video\n\n"
                f"Error: {audio_info.get('error', 'Unknown error')}\n\n"
                "Try again or contact support."
            )
            return
        
        edit_message(
            chat_id,
            message_id,
            f"🎵 <b>{audio_info['title']}</b>\n\n"
            f"⏳ Downloading audio...",
            [
                [{'text': "📢 Join Channel", 'url': "https://t.me/Yagami_xlight"}]
            ]
        )
        
        audio_response = send_audio_stream(chat_id, audio_info['download_url'])
        if not audio_response or not audio_response.get('ok'):
            edit_message(
                chat_id,
                message_id,
                f"🎵 <b>{audio_info['title']}</b>\n\n"
                f"🔗 <a href=\"{audio_info['download_url']}\">Download Audio</a>\n\n"
                "<i>Failed to send as audio file. Use the download link instead.</i>",
                [
                    [{'text': "📢 Join Channel", 'url': "https://t.me/Yagami_xlight"}]
                ]
            )

# Webhook Route
@app.route('/', methods=['POST'])
def webhook() -> Response:
    update = request.get_json()
    if not update:
        return jsonify({'status': 'error', 'message': 'Invalid update'}), 400
    
    # Extract update data
    message = update.get('message')
    callback_query = update.get('callback_query')
    
    if message:
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        text = message.get('text', '').strip()
        
        if text.startswith('/start'):
            handle_start(chat_id)
        elif text.startswith('/admin') and str(user_id) == Config.ADMIN_CHAT_ID:
            send_message(chat_id, "Admin panel coming soon...")
        elif validate_youtube_url(text):
            handle_youtube_url(chat_id, user_id, text)
        elif text:
            handle_search(chat_id, user_id, text)
    
    elif callback_query:
        chat_id = callback_query['message']['chat']['id']
        user_id = callback_query['from']['id']
        callback_id = callback_query['id']
        message_id = callback_query['message']['message_id']
        data = callback_query.get('data', '')
        
        handle_callback(callback_id, chat_id, user_id, message_id, data)
    
    return jsonify({'status': 'success'})

# Health Check
@app.route('/health')
def health_check() -> Response:
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))