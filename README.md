# IVASMS OTP Telegram Bot

ivasms.com থেকে OTP অটোমেটিক ফেচ করে টেলিগ্রামে পাঠানোর বট।

---

## ফাইল লিস্ট

| ফাইল | কাজ |
|------|-----|
| `bot.py` | মেইন বট কোড |
| `requirements.txt` | পাইথন লাইব্রেরি লিস্ট |
| `Procfile` | Railway/Heroku-এর জন্য |
| `runtime.txt` | পাইথন ভার্সন |
| `.gitignore` | গিট ইগনোর লিস্ট |

---

## Railway-এ ডিপ্লয় করার ধাপ

### ধাপ ১: GitHub-এ রিপোজিটরি তৈরি করো

১. [github.com](https://github.com) এ গিয়ে নতুন রিপোজিটরি তৈরি করো (যেমন: `ivasms-otp-bot`)
২. এই সব ফাইল আপলোড করো:
   - `bot.py`
   - `requirements.txt`
   - `Procfile`
   - `runtime.txt`
   - `.gitignore`

### ধাপ ২: Railway অ্যাকাউন্ট তৈরি করো

১. [railway.app](https://railway.app) এ গিয়ে GitHub দিয়ে লগইন করো
২. "New Project" → "Deploy from GitHub repo" সিলেক্ট করো
৩. তোমার `ivasms-otp-bot` রিপোজিটরি সিলেক্ট করো

### ধাপ ৩: Environment Variables সেট করো

Railway-এ তোমার প্রজেক্টে গিয়ে **Variables** ট্যাবে যাও, নিচের ভেরিয়েবলগুলো অ্যাড করো:

| Variable | Value | Example |
|----------|-------|---------|
| `TELEGRAM_BOT_TOKEN` | @BotFather থেকে পাওয়া টোকেন | `7123456789:AAHxxxxxxxxxxxxxxxx` |
| `TELEGRAM_CHAT_ID` | তোমার Chat ID | `4834118448` |
| `IVASMS_API_BASE_URL` | ivasms API URL | `https://www.ivasms.com` |
| `IVASMS_EMAIL` | ivasms ইমেইল (যদি API login লাগে) | `your@email.com` |
| `IVASMS_PASSWORD` | ivasms পাসওয়ার্ড (যদি API login লাগে) | `yourpassword` |
| `IVASMS_API_KEY` | ivasms API Key (যদি থাকে) | `optional` |
| `CHECK_INTERVAL` | কত সেকেন্ড পর চেক করবে | `30` |

### ধাপ ৪: Deploy করো

১. Railway-এ **Deploy** ট্যাবে গিয়ে **Deploy** বাটনে ক্লিক করো
২. লগ দেখো — "Bot starting..." দেখালে সাকসেস!

---

## লোকালি টেস্ট করতে

```bash
# ১. লাইব্রেরি ইনস্টল করো
pip install -r requirements.txt

# ২. Environment variables সেট করো (Linux/Mac)
export TELEGRAM_BOT_TOKEN="তোমার_টোকেন"
export TELEGRAM_CHAT_ID="4834118448"
export IVASMS_API_BASE_URL="https://www.ivasms.com"

# Windows (PowerShell):
# $env:TELEGRAM_BOT_TOKEN="তোমার_টোকেন"

# ৩. রান করো
python bot.py
