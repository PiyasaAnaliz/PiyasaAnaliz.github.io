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
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "BURAYA_YENI_TOKEN")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "BURAYA_YENI_KEY")

cache_data = {
    "emtia": "Veriler yükleniyor...",
    "kripto": "Veriler yükleniyor...",
    "doviz": "Veriler yükleniyor...",
    "bist": "BIST100: Gün sonu kapanış verileri baz alınmıştır.",
    "uyari": (
        "⚠️ YASAL UYARI\n\n"
        "Bu botta yer alan tüm veriler yalnızca bilgilendirme amaçlıdır.\n"
        "Yatırım tavsiyesi değildir."
    ),
    "last_update": "Henüz güncellenmedi"
}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ===================== VERİ ÇEKME (FINNHUB) =====================
def fetch_quote(symbol, name):
    """Finnhub quote endpoint'inden fiyat çeker."""
    try:
        url = "https://finnhub.io/api/v1/quote"
        params = {"symbol": symbol, "token": FINNHUB_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        price = data.get("c")           # current price
        prev = data.get("pc")           # previous close

        if not price or price == 0:
            return f"{name}: veri yok"

        change_pct = ((price - prev) / prev * 100) if prev else 0
        return f"{name}: {price:.2f} (%{change_pct:+.2f})"
    except Exception as e:
        logger.warning(f"{name} verisi alınamadı: {e}")
        return f"{name}: veri alınamadı"


def fetch_forex(symbol_from, symbol_to, name):
    """Finnhub forex endpoint'i (kripto/döviz için)."""
    try:
        url = "https://finnhub.io/api/v1/forex/rates"
        params = {"base": symbol_from, "token": FINNHUB_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        rate = data.get("quote", {}).get(symbol_to)
        if rate is None:
            return f"{name}: veri yok"
        return f"{name}: {rate:.4f}"
    except Exception as e:
        logger.warning(f"{name} verisi alınamadı: {e}")
        return f"{name}: veri alınamadı"


def fetch_crypto(symbol, name):
    """Finnhub kripto endpoint'i. Örn sembol: BINANCE:BTCUSDT"""
    try:
        url = "https://finnhub.io/api/v1/quote"
        params = {"symbol": symbol, "token": FINNHUB_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        price = data.get("c")
        prev = data.get("pc")
        if not price:
            return f"{name}: veri yok"

        change_pct = ((price - prev) / prev * 100) if prev else 0
        return f"{name}: {price:,.2f} (%{change_pct:+.2f})"
    except Exception as e:
        logger.warning(f"{name} verisi alınamadı: {e}")
        return f"{name}: veri alınamadı"


def update_all_caches():
    try:
        cache_data["emtia"] = "\n".join([
            fetch_crypto("OANDA:XAU_USD", "Altın (ONS)"),
            fetch_crypto("OANDA:XAG_USD", "Gümüş (ONS)"),
            fetch_crypto("OANDA:BCO_USD", "Brent Petrol"),
        ])
        cache_data["kripto"] = "\n".join([
            fetch_crypto("BINANCE:BTCUSDT", "Bitcoin"),
            fetch_crypto("BINANCE:ETHUSDT", "Ethereum"),
        ])
        cache_data["doviz"] = "\n".join([
            fetch_forex("USD", "TRY", "Dolar"),
            fetch_forex("EUR", "TRY", "Euro"),
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


# ===================== FLASK =====================
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
    update_all_caches()

    scheduler = BackgroundScheduler()
    scheduler.add_job(update_all_caches, 'cron', minute='*/30')
    scheduler.start()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask thread başlatıldı.")

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler)
    )

    logger.info("Bot başlatılıyor...")
    application.run_polling()
