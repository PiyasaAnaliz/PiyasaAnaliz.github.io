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

# Cache
cache_data = {
    "emtia": "Veriler yükleniyor...",
    "kripto": "Veriler yükleniyor...",
    "doviz": "Veriler yükleniyor...",
    "bist": "BIST100: Gün sonu kapanış verileri baz alınmıştır.",
    "last_update": "Henüz güncellenmedi"
}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ===================== VERİ ÇEKME =====================
def fetch_price(symbol, name):
    try:
        url = f"https://biquote.io/api/{symbol}"
        data = requests.get(url, timeout=10).json()
        price = data.get('mid', 'N/A')
        change = data.get('dayDiffPercent', 0)
        return f"{name}: {price:.2f} (%{change:+.2f})"
    except:
        return f"{name} verisi alınamadı."

def update_all_caches():
    cache_data = fetch_price("XAUUSD", "Altın (ONS)")
    cache_data = fetch_price("BTCUSD", "Bitcoin")
    cache_data = f"Dolar: {fetch_price('USDTRY', 'Dolar')}\nEuro: {fetch_price('EURTRY', 'Euro')}"
    cache_data["last_update"] = datetime.now().strftime("%d-%m-%Y %H:%M")

# ===================== TELEGRAM =====================
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Emtialar", callback_data='emtia')], ,
        [InlineKeyboardButton("Döviz Kurları", callback_data='doviz')],
        [InlineKeyboardButton("Borsa İstanbul", callback_data='bist')],
        [InlineKeyboardButton("Yasal Uyarı", callback_data='uyari')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! Piyasa takip botuna hoş geldin.\nAşağıdan istediğin kategoriyi seç.",
        reply_markup=get_main_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = cache_data.get(query.data, "Veri bulunamadı")
    footer = f"\n\nSon Güncelleme: {cache_data }\n⚠️ Bilgi amaçlıdır, yatırım tavsiyesi değildir."
    
    await query.edit_message_text(text=text + footer, reply_markup=get_main_keyboard())

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Menüden seçim yapabilirsin. Hangi piyasa hakkında bilgi istersin?",
        reply_markup=get_main_keyboard()
    )

# ===================== BAŞLATMA =====================
if __name__ == '__main__':
    update_all_caches()

    scheduler = BackgroundScheduler()
    scheduler.add_job(update_all_caches, 'cron', minute='*/30')  # Her 30 dakikada bir
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
