import logging
import os
import threading
import requests
from datetime import datetime
from flask import Flask

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler,
    CommandHandler, ContextTypes, MessageHandler, filters
)
from apscheduler.schedulers.background import BackgroundScheduler

# ===================== AYARLAR =====================
TELEGRAM_TOKEN = "8730070682:AAEtuRaWhYt3gZHSCQoePxK_SmYlfheyAuk"

cache_data = {
    "emtia": "Veriler yükleniyor...",
    "kripto": "Veriler yükleniyor...",
    "doviz": "Veriler yükleniyor...",
    "bist": "BIST100: Gün sonu kapanış verileri baz alınmıştır.",
    "uyari": "⚠️ YASAL UYARI\n\nBu botta yer alan tüm veriler yalnızca bilgilendirme amaçlıdır.",
    "last_update": "Henüz güncellenmedi"
}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== VERİ ÇEKME =====================
def fetch_price(symbol, name):
    try:
        url = f"https://biquote.io/api/{symbol}"
        data = requests.get(url, timeout=10).json()
        price = data.get('mid')
        change = data.get('dayDiffPercent', 0)

        if price is None:
            return f"{name}: veri yok"

        return f"{name}: {float(price):.2f} (%{float(change):+.2f})"
    except Exception as e:
        logger.warning(f"{name} verisi alınamadı: {e}")
        return f"{name}: veri alınamadı"


def update_all_caches():
    try:
        cache_data["emtia"] = "\n".join([
            fetch_price("XAUUSD", "Altın (ONS)"),
            fetch_price("XAGUSD", "Gümüş (ONS)"),
            fetch_price("BRENT", "Brent Petrol"),
        ])
        cache_data["kripto"] = "\n".join([
            fetch_price("BTCUSD", "Bitcoin"),
            fetch_price("ETHUSD", "Ethereum"),
        ])
        cache_data["doviz"] = "\n".join([
            fetch_price("USDTRY", "Dolar"),
            fetch_price("EURTRY", "Euro"),
        ])
        cache_data["last_update"] = datetime.now().strftime("%d-%m-%Y %H:%M")
        logger.info("Veriler güncellendi.")
    except Exception as e:
        logger.exception(f"Güncelleme hatası: {e}")


# ===================== TELEGRAM =====================
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Emtialar", callback_data='emtia')],
        [InlineKeyboardButton("Kripto Paralar", callback_data='kripto')],
        [InlineKeyboardButton("Döviz Kurları", callback_data='doviz')],
        [InlineKeyboardButton("BIST100", callback_data='bist')],
        [InlineKeyboardButton("Yasal Uyarı", callback_data='uyari')],
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
    footer = f"\n\nSon Güncelleme: {cache_data['last_update']}\n⚠️ Bilgi amaçlıdır."

    await query.edit_message_text(
        text=text + footer,
        reply_markup=get_main_keyboard()
    )


async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Menüden seçim yapabilirsin.",
        reply_markup=get_main_keyboard()
    )


# ===================== FLASK (Ayrı Thread) =====================
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def home():
    return "Bot çalışıyor"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


# ===================== BAŞLATMA =====================
if __name__ == '__main__':
    # 1. Verileri yükle
    update_all_caches()

    # 2. Scheduler başlat
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_all_caches, 'cron', minute='*/30')
    scheduler.start()

    # 3. Flask'ı AYRI daemon thread'de çalıştır
    #    ÖNEMLİ: use_reloader=False olmalı, yoksa iki bot başlar!
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask thread başlatıldı.")

    # 4. Telegram botunu ANA thread'de çalıştır
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    logger.info("Bot başlatılıyor...")
    application.run_polling()
