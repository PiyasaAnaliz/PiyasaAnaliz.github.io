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
    """Finnhub /quote endpoint. Emtia, kripto ve forex için tek endpoint."""
    url = "https://finnhub.io/api/v1/quote"
    params = {"symbol": symbol, "token": FINNHUB_API_KEY}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_asset(symbol, name, is_crypto=False):
    """Tek sembol için fiyat + değişim yüzdesi çeker."""
    try:
        data = _finnhub_quote(symbol)
        price = data.get("c")
        prev = data.get("pc")

        if not price or price == 0:
            logger.warning(f"⚠️ {name} ({symbol}): fiyat 0/None döndü → {data}")
            return f"{name}: veri yok"

        change_pct = ((price - prev) / prev * 100) if prev else 0
        decimals = 2 if is_crypto else 4
        return f"{name}: {price:,.{decimals}f} (%{change_pct:+.2f})"
    except Exception as e:
        logger.warning(f"❌ {name} ({symbol}) alınamadı: {e}")
        return f"{name}: veri alınamadı"


def fetch_forex(base, target, name):
    """Finnhub forex için 'OANDA:XXX_YYY' formatı kullanılır."""
    try:
        symbol = f"OANDA:{base}_{target}"
        data = _finnhub_quote(symbol)
        price = data.get("c")

        if not price or price == 0:
            logger.warning(f"⚠️ {name} ({symbol}): fiyat 0/None → {data}")
            return f"{name}: veri yok"

        return f"{name}: {price:.4f}"
    except Exception as e:
        logger.warning(f"❌ {name} alınamadı: {e}")
        return f"{name}: veri alınamadı"


def fetch_emtia(symbol, name):
    return fetch_asset(symbol, name, is_crypto=False)


def update_all_caches():
    """Tüm kategorileri günceller. Hata olsa bile bot çökmemeli."""
    try:
        cache_data["emtia"] = "\n".join([
            fetch_emtia("OANDA:XAU_USD", "Altın (ONS)"),
            fetch_emtia("OANDA:XAG_USD", "Gümüş (ONS)"),
            fetch_emtia("OANDA:BCO_USD", "Brent Petrol"),
        ])
        logger.info(f"Emtia güncellendi:\n{cache_data['emtia']}")
    except Exception as e:
        logger.exception(f"Emtia güncelleme hatası: {e}")

    try:
        cache_data["kripto"] = "\n".join([
            fetch_asset("BINANCE:BTCUSDT", "Bitcoin", is_crypto=True),
            fetch_asset("BINANCE:ETHUSDT", "Ethereum", is_crypto=True),
        ])
        logger.info(f"Kripto güncellendi:\n{cache_data['kripto']}")
    except Exception as e:
        logger.exception(f"Kripto güncelleme hatası: {e}")

    try:
        cache_data["doviz"] = "\n".join([
            fetch_forex("USD", "TRY", "Dolar"),
            fetch_forex("EUR", "TRY", "Euro"),
        ])
        logger.info(f"Döviz güncellendi:\n{cache_data['doviz']}")
    except Exception as e:
        logger.exception(f"Döviz güncelleme hatası: {e}")

    cache_data["last_update"] = datetime.now().strftime("%d-%m-%Y %H:%M")
    logger.info("✅ Tüm veriler güncellendi.")


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

    full_text = text + footer

    try:
        await query.edit_message_text(
            text=full_text,
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        # Telegram aynı içerikli mesajı düzenlemeye izin vermez
        logger.warning(f"edit_message_text hatası: {e}")
        try:
            await query.message.reply_text(
                text=full_text,
                reply_markup=get_main_keyboard()
            )
        except Exception as e2:
            logger.error(f"reply_text de başarısız: {e2}")


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

    # İlk veri çekimi
    update_all_caches()

    # Scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_all_caches, 'cron', minute='*/30')
    scheduler.start()
    logger.info("⏰ Scheduler başlatıldı (her 30 dakikada bir).")

    # Flask (health check)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask thread başlatıldı.")

    # Telegram bot
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler)
    )

    logger.info("✅ Telegram botu polling başlıyor...")
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()
