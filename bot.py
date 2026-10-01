import logging
import asyncio
import requests
import json
import re
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ==========================================
# CONFIGURATION - Pre-filled credentials
# ==========================================
TELEGRAM_BOT_TOKEN = "8219571800:AAEPeynlx5AyWmOwukjJaFn0LraDqucDE14"
TELEGRAM_CHAT_ID = "7414899469"
IVASMS_BASE_URL = os.environ.get("IVASMS_API_BASE_URL", "https://www.ivasms.com").rstrip('/')
IVASMS_API_KEY = os.environ.get("IVASMS_API_KEY", "")
IVASMS_EMAIL = os.environ.get("IVASMS_EMAIL", "")
IVASMS_PASSWORD = os.environ.get("IVASMS_PASSWORD", "")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))

LIVE_SMS_URL = f"{IVASMS_BASE_URL}/portal/live/test_sms"

# ==========================================
# LOGGING
# ==========================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==========================================
# OTP TRACKER
# ==========================================
class OTPTracker:
    def __init__(self, expiry_minutes=10):
        self.seen = {}
        self.expiry = timedelta(minutes=expiry_minutes)

    def is_new(self, otp):
        now = datetime.now()
        expired = [k for k, v in self.seen.items() if now - v > self.expiry]
        for k in expired:
            del self.seen[k]
        if otp in self.seen:
            return False
        self.seen[otp] = now
        return True

# ==========================================
# IVASMS CLIENT
# ==========================================
class IVASMSClient:
    def __init__(self, base_url, api_key=None, email=None, password=None):
        self.base_url = base_url
        self.api_key = api_key
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.auth_token = None

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/html',
            'Content-Type': 'application/json',
        })

        if api_key:
            self.session.headers.update({'Authorization': f'Bearer {api_key}'})

    def login(self):
        try:
            login_endpoints = ['/auth/login', '/login', '/api/login', '/user/login', '/authenticate']
            for endpoint in login_endpoints:
                url = f"{self.base_url}{endpoint}"
                data = {'email': self.email, 'password': self.password}
                response = self.session.post(url, json=data, timeout=15)
                if response.status_code in [200, 201]:
                    try:
                        resp_json = response.json()
                        token = (resp_json.get('token') or resp_json.get('access_token') or
                                resp_json.get('api_token') or resp_json.get('data', {}).get('token'))
                        if token:
                            self.auth_token = token
                            self.session.headers.update({'Authorization': f'Bearer {token}'})
                            logger.info(f"API login successful via {endpoint}")
                            return True
                    except:
                        pass
            logger.warning("API login not available, trying without auth...")
            return False
        except Exception as e:
            logger.error(f"API login error: {e}")
            return False

    def fetch_messages(self):
        message_endpoints = [
            '/api/messages', '/api/sms', '/api/sms/list', '/api/messages/recent',
            '/api/otp', '/api/numbers/messages', '/api/history', '/api/dashboard/data',
            '/messages', '/sms', '/sms/list', '/messages/recent', '/otp',
            '/history', '/dashboard/data',
        ]
        all_messages = []

        for endpoint in message_endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                response = self.session.get(url, timeout=15)
                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '')
                    if 'json' in content_type:
                        data = response.json()
                        messages = self._parse_json_response(data)
                        if messages:
                            all_messages.extend(messages)
                            logger.info(f"Found {len(messages)} messages from {endpoint}")
                    else:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.content, 'html.parser')
                        messages = self._parse_html(soup)
                        if messages:
                            all_messages.extend(messages)
                            logger.info(f"Found {len(messages)} messages from HTML {endpoint}")
            except Exception as e:
                logger.warning(f"Endpoint {endpoint} error: {e}")
                continue
        return all_messages

    def fetch_live_test_sms(self):
        """Fetch live test SMS from the portal page"""
        try:
            api_endpoints = [
                '/api/portal/live/test_sms',
                '/api/live/test_sms',
                '/api/test_sms',
                '/api/live-sms',
            ]
            for endpoint in api_endpoints:
                try:
                    url = f"{self.base_url}{endpoint}"
                    response = self.session.get(url, timeout=15)
                    if response.status_code == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'json' in content_type:
                            return self._parse_live_json(response.json())
                except:
                    continue

            url = f"{self.base_url}/portal/live/test_sms"
            response = self.session.get(url, timeout=15)
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')
                return self._parse_live_html(soup)

            return None
        except Exception as e:
            logger.error(f"Live SMS fetch error: {e}")
            return None

    def _parse_live_json(self, data):
        live_sms = []
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (data.get('data') or data.get('messages') or data.get('items') or
                    data.get('result') or data.get('sms') or [])

        if not isinstance(items, list):
            return live_sms

        for item in items:
            if not isinstance(item, dict):
                continue
            country = (item.get('country') or item.get('country_name') or item.get('region') or 'Unknown')
            number = (item.get('number') or item.get('phone') or item.get('phone_number') or item.get('msisdn') or 'N/A')
            sid = (item.get('sid') or item.get('service') or item.get('app') or item.get('source') or 'Unknown')
            code = (item.get('code') or item.get('otp') or item.get('pin') or '')
            live_sms.append({'country': country, 'number': number, 'sid': sid, 'code': code})
        return live_sms

    def _parse_live_html(self, soup):
        from bs4 import BeautifulSoup
        live_sms = []

        try:
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        texts = [c.get_text(strip=True) for c in cells]
                        country = texts[0] if len(texts) > 0 else 'Unknown'
                        sid = texts[1] if len(texts) > 1 else 'Unknown'
                        code = texts[2] if len(texts) > 2 else ''

                        number_match = re.search(r'[+]?\d{5,15}', country)
                        number = number_match.group() if number_match else 'N/A'
                        country_clean = re.sub(r'[+]?\d+', '', country).strip()

                        live_sms.append({
                            'country': country_clean or 'Unknown',
                            'number': number,
                            'sid': sid,
                            'code': code
                        })

            if not live_sms:
                cards = soup.find_all('div', class_=re.compile(r'card|item|row|sms', re.I))
                for card in cards:
                    text = card.get_text(strip=True)
                    if not text:
                        continue
                    number_match = re.search(r'[+]?\d{5,15}', text)
                    number = number_match.group() if number_match else 'N/A'
                    country = 'Unknown'
                    sid = 'Unknown'

                    services = ['melbet', 'whatsapp', 'facebook', 'google', 'instagram', 'telegram']
                    for s in services:
                        if s in text.lower():
                            sid = s.title()
                            break

                    live_sms.append({'country': country, 'number': number, 'sid': sid, 'code': ''})
        except Exception as e:
            logger.error(f"Live HTML parse error: {e}")

        return live_sms

    def _parse_json_response(self, data):
        messages = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (data.get('data') or data.get('messages') or data.get('items') or
                    data.get('result') or data.get('sms') or [])
        else:
            return messages

        if not isinstance(items, list):
            return messages

        for item in items:
            if not isinstance(item, dict):
                continue
            otp = self._extract_otp_from_item(item)
            if not otp:
                continue
            phone = (item.get('phone') or item.get('number') or item.get('from') or
                    item.get('sender') or item.get('phone_number') or "N/A")
            service = (item.get('service') or item.get('app') or item.get('source') or
                      item.get('provider') or "Unknown")
            timestamp = (item.get('time') or item.get('timestamp') or item.get('created_at') or
                        item.get('date') or datetime.now().strftime('%H:%M:%S'))
            messages.append({
                'otp': otp, 'phone': str(phone), 'service': str(service),
                'timestamp': str(timestamp), 'raw': json.dumps(item)[:200]
            })
        return messages

    def _parse_html(self, soup):
        from bs4 import BeautifulSoup
        import re
        messages = []
        text = soup.get_text()
        otp_matches = re.findall(r'\b\d{4,8}\b', text)
        for otp in set(otp_matches):
            idx = text.find(otp)
            context = text[max(0, idx-100):idx+100]
            phone_match = re.search(r'[+]?\d{10,15}', context)
            phone = phone_match.group() if phone_match else "N/A"
            services = ['facebook','google','instagram','twitter','whatsapp','telegram','discord','tiktok','snapchat','netflix','amazon','apple']
            service = "Unknown"
            for s in services:
                if s in context.lower():
                    service = s.title()
                    break
            messages.append({
                'otp': otp, 'phone': phone, 'service': service,
                'timestamp': datetime.now().strftime('%H:%M:%S'), 'raw': context[:100]
            })
        return messages

    def _extract_otp_from_item(self, item):
        otp_fields = ['otp', 'code', 'pin', 'verification_code', 'token', 'number']
        for field in otp_fields:
            if field in item and item[field]:
                val = str(item[field])
                if re.match(r'^\d{4,8}$', val):
                    return val
        text_fields = ['message', 'body', 'text', 'content', 'sms', 'data']
        for field in text_fields:
            if field in item and item[field]:
                text = str(item[field])
                match = re.search(r'\b\d{4,8}\b', text)
                if match:
                    return match.group()
        return None

# ==========================================
# GLOBAL CLIENT & TRACKER
# ==========================================
client = None
tracker = None

def get_client():
    global client
    if client is None:
        client = IVASMSClient(
            base_url=IVASMS_BASE_URL,
            api_key=IVASMS_API_KEY or None,
            email=IVASMS_EMAIL or None,
            password=IVASMS_PASSWORD or None,
        )
        if IVASMS_EMAIL and IVASMS_PASSWORD:
            client.login()
    return client

def get_tracker():
    global tracker
    if tracker is None:
        tracker = OTPTracker(expiry_minutes=10)
    return tracker

# ==========================================
# TELEGRAM COMMANDS
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔴 Live Test SMS দেখো", callback_data='live_sms')],
        [InlineKeyboardButton("🔗 ওয়েবসাইটে যাও", url=LIVE_SMS_URL)],
        [InlineKeyboardButton("📊 Status", callback_data='status'),
         InlineKeyboardButton("❓ Help", callback_data='help')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔐 <b>IVASMS OTP Bot</b>\n\n"
        "নিচের বাটনে ক্লিক করে Live Test SMS দেখতে পারবে।\n"
        "বট অটোমেটিক নতুন OTP পেলে পাঠিয়ে দেবে।",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>ব্যবহার নির্দেশিকা:</b>\n\n"
        "<b>বাটন:</b>\n"
        "• 🔴 Live Test SMS দেখো - লাইভ SMS লিস্ট দেখাবে\n"
        "• 🔗 ওয়েবসাইটে যাও - সরাসরি ivasms লিংক\n"
        "• 📊 Status - বট স্ট্যাটাস\n\n"
        "<b>কমান্ড:</b>\n"
        "• /start - মেইন মেনু\n"
        "• /live - লাইভ SMS দেখো\n"
        "• /status - স্ট্যাটাস\n"
        "• /check - ম্যানুয়াল OTP চেক\n"
        "• /help - সাহায্য"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode='HTML')
    else:
        await update.message.reply_text(text, parse_mode='HTML')

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📊 <b>Bot Status:</b>\n"
        "✅ Running!\n"
        f"💬 Chat ID: {TELEGRAM_CHAT_ID}\n"
        f"🌐 API: {IVASMS_BASE_URL}\n"
        f"⏱️ Interval: {CHECK_INTERVAL}s"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode='HTML')
    else:
        await update.message.reply_text(text, parse_mode='HTML')

async def live_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show live test SMS"""
    cl = get_client()

    if update.callback_query:
        await update.callback_query.answer("🔍 লোড হচ্ছে...")
        msg_obj = update.callback_query
    else:
        msg_obj = update.message

    try:
        live_data = cl.fetch_live_test_sms()

        if live_data and len(live_data) > 0:
            text = "🔴 <b>Live Test SMS</b>\n\n"
            for i, item in enumerate(live_data[:10], 1):
                flag = "🇺🇳"
                country_name = item['country'].upper()
                flag_map = {
                    'CAMEROON': "🇨🇲", 'KAZAKHSTAN': "🇰🇿", 'USA': "🇺🇸",
                    'UNITED STATES': "🇺🇸", 'UK': "🇬🇧", 'UNITED KINGDOM': "🇬🇧",
                    'INDIA': "🇮🇳", 'BANGLADESH': "🇧🇩", 'RUSSIA': "🇷🇺",
                    'GERMANY': "🇩🇪", 'FRANCE': "🇫🇷", 'CAMBODIA': "🇰🇭",
                    'INDONESIA': "🇮🇩", 'PHILIPPINES': "🇵🇭", 'VIETNAM': "🇻🇳",
                    'UKRAINE': "🇺🇦", 'KENYA': "🇰🇪", 'NIGERIA': "🇳🇬",
                }
                for key, val in flag_map.items():
                    if key in country_name:
                        flag = val
                        break

                code_text = f"\n   🔢 Code: <code>{item['code']}</code>" if item.get('code') else ""
                text += (
                    f"{i}. {flag} <b>{item['country']}</b>\n"
                    f"   📱 <code>{item['number']}</code>\n"
                    f"   🏷️ SID: {item['sid']}{code_text}\n\n"
                )

            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data='live_sms')],
                [InlineKeyboardButton("🔗 ওয়েবসাইটে যাও", url=LIVE_SMS_URL)],
                [InlineKeyboardButton("⬅️ Back", callback_data='start_menu')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
            else:
                await msg_obj.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)
        else:
            keyboard = [
                [InlineKeyboardButton("🔗 ওয়েবসাইটে যাও", url=LIVE_SMS_URL)],
                [InlineKeyboardButton("🔄 Retry", callback_data='live_sms')],
                [InlineKeyboardButton("⬅️ Back", callback_data='start_menu')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            text = (
                "⚠️ <b>Live Test SMS লোড করা যায়নি।</b>\n\n"
                "সম্ভব কারণ:\n"
                "• CAPTCHA ব্লক করছে\n"
                "• লগইন প্রয়োজন\n"
                "• সার্ভার ডাউন\n\n"
                "ওয়েবসাইটে সরাসরি দেখতে লিংকে ক্লিক করো।"
            )
            if update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
            else:
                await msg_obj.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Live command error: {e}")
        keyboard = [
            [InlineKeyboardButton("🔗 ওয়েবসাইটে যাও", url=LIVE_SMS_URL)],
            [InlineKeyboardButton("⬅️ Back", callback_data='start_menu')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.edit_message_text(f"❌ Error: {str(e)[:100]}", reply_markup=reply_markup)
        else:
            await msg_obj.reply_text(f"❌ Error: {str(e)[:100]}", reply_markup=reply_markup)

async def manual_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 ম্যানুয়াল OTP চেক শুরু হচ্ছে...")

# ==========================================
# CALLBACK QUERY HANDLER
# ==========================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == 'live_sms':
        await live_cmd(update, context)
    elif data == 'status':
        await status_cmd(update, context)
    elif data == 'help':
        await help_command(update, context)
    elif data == 'start_menu':
        keyboard = [
            [InlineKeyboardButton("🔴 Live Test SMS দেখো", callback_data='live_sms')],
            [InlineKeyboardButton("🔗 ওয়েবসাইটে যাও", url=LIVE_SMS_URL)],
            [InlineKeyboardButton("📊 Status", callback_data='status'),
             InlineKeyboardButton("❓ Help", callback_data='help')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.answer()
        await query.edit_message_text(
            "🔐 <b>IVASMS OTP Bot</b>\n\n"
            "নিচের বাটনে ক্লিক করে Live Test SMS দেখতে পারবে।\n"
            "বট অটোমেটিক নতুন OTP পেলে পাঠিয়ে দেবে।",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    else:
        await query.answer("Processing...")

# ==========================================
# BACKGROUND MONITOR
# ==========================================
async def monitor_otps(application: Application):
    cl = get_client()
    tr = get_tracker()
    await asyncio.sleep(5)

    while True:
        try:
            logger.info("Checking ivasms for OTPs...")
            messages = cl.fetch_messages()
            if messages:
                for msg in messages:
                    otp = msg['otp']
                    if tr.is_new(otp):
                        text = (
                            f"🔐 <b>New OTP Received</b>\n\n"
                            f"🔢 OTP: <code>{otp}</code>\n"
                            f"📱 Number: {msg['phone']}\n"
                            f"🌐 Service: {msg['service']}\n"
                            f"⏰ Time: {msg['timestamp']}\n\n"
                            f"Tap the OTP to copy it!"
                        )
                        await application.bot.send_message(
                            chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode='HTML'
                        )
                        logger.info(f"OTP sent: {otp}")
            else:
                logger.info("No new OTPs found")
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

# ==========================================
# MAIN
# ==========================================
def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return

    get_client()
    get_tracker()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("live", live_cmd))
    application.add_handler(CommandHandler("check", manual_check))
    application.add_handler(CallbackQueryHandler(button_handler))

    loop = asyncio.get_event_loop()
    monitor_task = loop.create_task(monitor_otps(application))

    logger.info("Bot starting...")
    logger.info(f"Chat ID: {TELEGRAM_CHAT_ID}")
    logger.info(f"Base URL: {IVASMS_BASE_URL}")
    logger.info(f"Live SMS URL: {LIVE_SMS_URL}")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
