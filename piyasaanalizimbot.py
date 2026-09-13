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
# Yerel test için default değerleri buraya yaz, prod'da env var kullan
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

if not TELEGRAM_TOKEN:
    raise SystemExit("❌ TELEGRAM_TOKEN eksik! Ortam değişkeni olarak tanımla.")
if not FINNHUB_API_KEY:
    raise SystemExit("❌ FINNHUB_API_KEY eksik! Ortam değişkeni olarak tanımla.")

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
def _finnhub_quote(symbol):
    """Finnhub /quote endpoint'i — hisse, kripto, bazı emtia için çalışır."""
    url = "https://finnhub.io/api/v1/quote"
    params = {"symbol": symbol, "token": FINNHUB_API_KEY}
    r = requests.get(url, params=params, timeout=10)
    return r.json()


def fetch_asset(symbol, name, is_crypto=False):
    """
    Tek fonksiyon: kripto ve emtia için kullanılır.
    is_crypto=True ise ondalık basamak 2, değilse 4.
    """
    try:
        data = _finnhub_quote(symbol)

        price = data.get("c")
        prev = data.get("pc")

        if not price or price == 0:
            return f"{name}: veri yok"

        change_pct = ((price - prev) / prev * 100) if prev else 0
        decimals = 2 if is_crypto else 4
        return f"{name}: {price:,.{decimals}f} (%{change_pct:+.2f})"
    except Exception as e:
        logger.warning(f"{name} verisi alınamadı: {e}")
        return f"{name}: veri alınamadı"


def fetch_forex(base, target, name):
    """Finnhub forex rates endpoint'i."""
    try:
        url = "https://finnhub.io/api/v1/forex/rates"
        params = {"base": base, "token": FINNHUB_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        rate = data.get("quote", {}).get(target)
        if rate is None:
            return f"{name}: veri yok"
        return f"{name}: {rate:.4f}"
    except Exception as e:
        logger.warning(f"{name} verisi alınamadı: {e}")
        return f"{name}: veri alınamadı"


def fetch_emtia(symbol, name):
    """
    Emtia için Finnhub kripto endpoint'ini kullanır.
    Finnhub ücretsiz planda OANDA sembolleri çalışmayabilir.
    Çalışmazsa 'veri yok' döner, sistem çökmez.
    """
    return fetch_asset(symbol, name, is_crypto=False)


def update_all_caches():
    try:
        # Emtia (ücretsiz planda OANDA olmayabilir — çalışmazsa 'veri yok' döner)
        cache_data["emtia"] = "\n".join([
            fetch_emtia("OANDA:XAU_USD", "Altın (ONS)"),
            fetch_emtia("OANDA:XAG_USD", "Gümüş (ONS)"),
            fetch_emtia("OANDA:BCO_USD", "Brent Petrol"),
        ])

        # Kripto (ücretsiz planda çalışır)
        cache_data["kripto"] = "\n".join([
            fetch_asset("BINANCE:BTCUSDT", "Bitcoin", is_crypto=True),
            fetch_asset("BINANCE:ETHUSDT", "Ethereum", is_crypto=True),
        ])

        # Döviz
        cache_data["doviz"] = "\n".join([
            fetch_forex("USD", "TRY", "Dolar"),
            fetch_forex("EUR", "TRY", "Euro"),
        ])

        cache_data["last_update"] = datetime.now().strftime("%d-%m-%Y %H:%M")
        logger.info("✅ Veriler güncellendi.")
    except Exception as e:
        logger.exception(f"❌ Güncelleme hatası: {e}")


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


# ===================== FLASK (Health Check) =====================
flask_app = Flask(__name__)


@flask_app.route('/')
@flask_app.route('/health')
def home():
    return "Bot çalışıyor"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


# ===================== BAŞLATMA =====================
def main():
    logger.info("🚀 Bot başlatılıyor...")

    # 1. İlk veri yüklemesi
    update_all_caches()

    # 2. Scheduler (her 30 dk)
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_all_caches, 'cron', minute='*/30')
    scheduler.start()
    logger.info("⏰ Scheduler başlatıldı.")

    # 3. Flask thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask thread başlatıldı.")

    # 4. Telegram bot
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler)
    )

    logger.info("✅ Telegram botu polling başlıyor...")
    application.run_polling()


if __name__ == '__main__':
    main()
