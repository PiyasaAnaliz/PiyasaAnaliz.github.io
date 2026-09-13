import logging
from datetime import datetime
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
import threading
import os

# ===================== AYARLAR =====================
TELEGRAM_TOKEN = "8730070682:AAEtuRaWhYt3gZHSCQoePxK_SmYlfheyAuk"
FINNHUB_API_KEY = "daisvd9r01qqjcj5bmugdaisvd9r01qqjcj5bmv0"

# Günlük toplam 25 istek limiti
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

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ===================== LIMIT KONTROL =====================
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

# ===================== VERİ ÇEKME =====================
def fetch_metal_data():
    if not can_make_request():
        return cache_data try:
        url = f"https://finnhub.io/api/v1/quote?symbol=OANDA:XAUUSD&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10).json()
        price = response.get('c', 'N/A')
        increment_call()
        return f"Altın (ONS): ${price}"
    except:
        return "Emtia verisi alınamadı."

def fetch_crypto_data():
    if not can_make_request():
        return cache_data try:
        url = f"https://finnhub.io/api/v1/quote?symbol=BINANCE:BTCUSDT&token={FINNHUB_API_KEY}"
        response = requests.get(url, timeout=10).json()
        price = response.get('c', 'N/A')
        increment_call()
        return f"Bitcoin (BTC): ${price}"
    except:
        return "Kripto verisi alınamadı."

def update_all_caches():
    if not can_make_request():
        logging.warning("Günlük limit doldu, cache güncellenmedi.")
        return
    
    cache_data = fetch_metal_data()
    cache_data["kripto"] = fetch_crypto_data()
    cache_data = datetime.now().strftime("%d-%m-%Y %H:%M")
    logging.info(f"Cache güncellendi. Bugün kullanılan: {daily_call_count}/{MAX_DAILY_CALLS}")

# ===================== TELEGRAM =====================
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Emtialar ve Metaller", callback_data='emitallar')],
        [InlineKeyboardButton("Kripto Paralar", callback_data='kripto')],
        [InlineKeyboardButton("Borsa İstanbul (BİST)", callback_data='bist')],
        [InlineKeyboardButton("Yasal Uyarı", callback_data='uyari')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hoş geldiniz!\n\nPiyasa takip botuna hoş geldiniz.\nAşağıdaki menüden istediğiniz kategoriyi seçebilirsiniz.",
        reply_markup=get_main_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    update_text = f"\n\nSon Güncelleme: {cache_data['last_update']}"
    warning = "\n\n⚠️ Bilgi amaçlıdır, yatırım tavsiyesi değildir."

    if query.data == 'emitallar':
        text = cache_data + update_text + warning
    elif query.data == 'kripto':
        text = cache_data["kripto"] + update_text + warning
    elif query.data == 'bist':
        text = cache_data + update_text + warning
    elif query.data == 'uyari':
        text = "Bu sistem tamamen bilgilendirme amaçlıdır.\nVerilerin doğruluğu garanti edilmez."
    else:
        text = "Bilinmeyen işlem."

    await query.edit_message_text(text=text, reply_markup=get_main_keyboard())

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Menüden seçim yapabilirsin veya /start yazabilirsin.",
        reply_markup=get_main_keyboard()
    )

# ===================== BAŞLATMA =====================
if __name__ == '__main__':
    update_all_caches()

    scheduler = BackgroundScheduler()
    scheduler.add_job(update_all_caches, 'cron', hour='9,11,13,15,17,20,23,2,5', minute=0)
    scheduler.start()

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    # Flask (Render için)
    app = Flask(__name__)
    @app.route('/')
    def home():
        return "Bot çalışıyor"

    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=10000), daemon=True).start()

    logging.info("Bot başlatıldı...")
    application.run_polling()
