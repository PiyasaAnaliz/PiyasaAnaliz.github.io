import logging
import os
from datetime import datetime
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters
)
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
import threading

# ==================== AYARLAR ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")          # Environment'dan al
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")        # Environment'dan al

# Günlük toplam API çağrı limiti (sen 25 istemiştin)
MAX_DAILY_CALLS = 25
daily_call_count = 0
last_reset_date = datetime.now().date()

# Cache
cache_data = {
    "emitallar": "Veriler yükleniyor...",
    "kripto": "Veriler yükleniyor...",
    "bist": "BIST100: Gün sonu kapanış verileri baz alınmıştır. Anlık işlem içermez.",
    "last_update": "Henüz güncellenmedi"
}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ==================== API ÇAĞRI KONTROLÜ ====================
def can_make_request():
    global daily_call_count, last_reset_date
    today = datetime.now().date()
    if today != last_reset_date:
        daily_call_count = 0
        last_reset_date = today
    return daily_call_count < MAX_DAILY_CALLS

def increment_call():
    global daily_call_count
    daily_call_count += 1

# ==================== VERİ ÇEKME ====================
def fetch_metal_data():
    if not can_make_request():
        return cache_data["emitallar"]  # eski cache'i döndür
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol=OANDA:XAUUSD&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10).json()
        price = response.get('c', 'N/A')
        increment_call()
        return f"Altın (ONS): ${price}"
    except Exception as e:
        logging.error(f"Emtia hatası: {e}")
        return "Emtia verisi şu an alınamıyor."

def fetch_crypto_data():
    if not can_make_request():
        return cache_data["kripto"]
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol=BINANCE:BTCUSDT&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10).json()
        price = response.get('c', 'N/A')
        increment_call()
        return f"Bitcoin (BTC): ${price}"
    except Exception as e:
        logging.error(f"Kripto hatası: {e}")
        return "Kripto verisi şu an alınamıyor."

def update_all_caches():
    """Sadece limit varsa güncelle"""
    if not can_make_request():
        logging.warning("Günlük limit dolu, cache güncellenmedi.")
        return

    logging.info(f"Cache güncelleniyor... (kalan hak: {MAX_DAILY_CALLS - daily_call_count})")
    cache_data["emitallar"] = fetch_metal_data()
    cache_data["kripto"] = fetch_crypto_data()
    cache_data["last_update"] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    logging.info(f"Güncellendi. Bugün kullanılan: {daily_call_count}/{MAX_DAILY_CALLS}")

# ==================== TELEGRAM ====================
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Emtialar ve Metaller", callback_data='emitallar')],
        [InlineKeyboardButton("Kripto Paralar", callback_data='kripto')],
        [InlineKeyboardButton("Borsa İstanbul (BİST)", callback_data='bist')],
        [InlineKeyboardButton("Yasal Uyarı", callback_data='uyari')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # İlk girişte kartvizit tarzı mesaj
    welcome_text = (
        "Hoş geldiniz!\n\n"
        "Piyasa takip botuna hoş geldiniz.\n"
        "Aşağıdaki menüden istediğiniz kategoriyi seçebilirsiniz.\n\n"
        "Not: Veriler belirli aralıklarla güncellenir (limit koruması nedeniyle)."
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    update_text = f"\n\n*(Son Güncelleme: {cache_data['last_update']})*"
    warning_footer = "\n\n⚠️ *Bilgi Amaçlıdır:* Yatırım tavsiyesi değildir."

    if query.data == 'emitallar':
        text = cache_data["emitallar"] + update_text + warning_footer
    elif query.data == 'kripto':
        text = cache_data["kripto"] + update_text + warning_footer
    elif query.data == 'bist':
        text = cache_data["bist"] + update_text + warning_footer
    elif query.data == 'uyari':
        text = "Sistem tamamen bilgilendirme amaçlı çalışır. Sunulan verilerin doğruluğu garanti edilmez."
    else:
        text = "Bilinmeyen seçenek."

    await query.edit_message_text(text=text, parse_mode='Markdown', reply_markup=get_main_keyboard())

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Serbest sohbet (basit cevap)"""
    await update.message.reply_text(
        "Şu an sadece menü butonlarıyla çalışıyorum.\n"
        "Yukarıdaki butonlardan birini seçebilirsin veya /start yazabilirsin.",
        reply_markup=get_main_keyboard()
    )

# ==================== SCHEDULER (Limit korumalı) ====================
def scheduled_job():
    update_all_caches()

# ==================== BAŞLATMA ====================
if __name__ == '__main__':
    if not TELEGRAM_TOKEN or not FINNHUB_API_KEY:
        raise ValueError("TELEGRAM_TOKEN ve FINNHUB_API_KEY environment variable olarak ayarlanmalı!")

    # İlk yükleme
    update_all_caches()

    scheduler = BackgroundScheduler()
    # Günde toplam ~12 güncelleme (her biri 2 çağrı = max 24)
    # Gündüz daha sık, gece seyrek
    scheduler.add_job(scheduled_job, 'cron', hour='9,11,13,15,17', minute=0)   # 5 kez gündüz
    scheduler.add_job(scheduled_job, 'cron', hour='20,23,3,6', minute=0)       # 4 kez gece
    scheduler.start()

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    # Flask (Render vb. için)
    app = Flask(__name__)
    @app.route('/')
    def home():
        return "Bot çalışıyor"

    def run_web():
        app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))

    threading.Thread(target=run_web, daemon=True).start()

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()
