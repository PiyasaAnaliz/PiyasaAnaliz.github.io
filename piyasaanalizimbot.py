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

# Destek ve İletişim Metni
DESTEK_METNI = (
    "💎 *Bize Destek Olun* 💎\n\n"
    "Merhaba! YouTube Katıl Butonu, Videonun Altındaki Süper Teşekkür ve "
    "Patreon üzerinden kanalımıza destek olabilirsiniz.\n\n"
    "Desteğiniz Çok Önemli: Sosyal Medya Hesaplarımı Takip Edip Beğenip "
    "Yorum ve Abone Olmayı Unutmayın Lütfen.\n\n"
    "🔗 *Kartvizit:* https://piyasaanaliz.github.io\n"
    "🐙 *GitHub:* https://www.github.com/PiyasaAnaliz\n"
    "🌐 *Web:* https://MutinousTube.github.io\n"
    "🐙 *GitHub:* https://www.github.com/MutinousTube\n"
    "▶️ *YouTube:* https://www.youtube.com/@PiyasaAnalizim\n"
    "🎵 *TikTok:* https://www.tiktok.com/@piyasaanalizim\n"
    "🎵 *TikTok:* https://www.tiktok.com/@piyasaanalizcim\n"
    "📺 *Rumble:* https://www.rumble.com/user/MutinousTube\n"
    "📺 *Dailymotion:* https://www.dailymotion.com/MutinousTube\n"
    "🐦 *X:* https://www.x.com/PiyasaAnalizim\n"
    "🐦 *X:* https://www.x.com/Piyasa_Analizi\n"
    "📸 *Instagram:* https://www.instagram.com/PiyasaAnalizim\n"
    "💬 *Telegram:* https://t.me/PiyasaAnalizci\n"
    "🟢 *WhatsApp:* https://whatsapp.com/channel/0029VbCUgXf6WaKnetLyMi34\n"
    "💬 *Telegram:* https://t.me/MutinousTube\n"
    "🟢 *WhatsApp:* https://whatsapp.com/channel/0029Vb4JKWmIyPtbv15mol0F\n\n"
    "🏢 *Mutinous Technology:*\n"
    "▶️ https://youtube.com/@MutinousTube\n"
    "📘 https://www.facebook.com/MutinousTube\n"
    "👥 https://youtube.com/@MutinousTube/community\n"
    "📧 *İletişim:* MutinousTube@gmail.com\n\n"
    "⚠️ *YASAL UYARI*\n"
    "BİLGİ AMAÇLI YAPILAN PAYLAŞIMLAR YATIRIM DANIŞMANLIĞI KAPSAMINDA DEĞİLDİR. "
    "HİÇ BİR ŞEKİLDE SORUMLULUK KABUL EDİLMEKTEDİR."
)

cache_data = {
    "emtia": "Veriler yükleniyor...",
    "kripto": "Veriler yükleniyor...",
    "doviz": "Veriler yükleniyor...",
    "bist": "BIST100: Gün sonu kapanış verileri baz alınmıştır.",
    "uyari": (
        "⚠️ YASAL UYARI\n\n"
        "Bu botta yer alan tüm veriler yalnızca bilgilendirme amaçlıdır.\n"
        "Yatırım tavsiyesi değildir.\n\n"
        "BİLGİ AMAÇLI YAPILAN PAYLAŞIMLAR YATIRIM DANIŞMANLIĞI KAPSAMINDA DEĞİLDİR. "
        "HİÇ BİR ŞEKİLDE SORUMLULUK KABUL EDİLMEKTEDİR."
    ),
    "destek": DESTEK_METNI,
    "last_update": "Henüz güncellenmedi"
}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ===================== AKILLI ALGILAMA (KELİME HAZNESİ) =====================
KEYWORD_MAP = {
    "doviz": [
        "dolar", "usd", "euro", "eur", "döviz", "doviz", "kur", "kurlar", 
        "parite", "sterlin", "gbp", "japon", "yen", "try", "tl"
    ],
    "emtia": [
        "altın", "altin", "gold", "gümüş", "gumus", "silver", "petrol", 
        "brent", "emtia", "ons", "xau", "xag", "bco", "metal"
    ],
    "kripto": [
        "bitcoin", "btc", "ethereum", "eth", "kripto", "crypto", "coin", 
        "binance", "usdt", "dijital", "altcoin"
    ],
    "bist": [
        "bist", "borsa", "hisse", "endeks", "bist100", "xu100", "istanbul"
    ],
    "destek": [
        "destek", "iletişim", "iletisim", "sosyal", "medya", "youtube", 
        "patreon", "bağış", "bagis", "kanal", "abone", "takip"
    ],
    "uyari": [
        "uyarı", "uyari", "yasal", "risk", "sorumluluk", "tavsiye"
    ]
}

def detect_category(text: str):
    """Kullanıcının yazdığı metne göre hangi kategoriye ait olduğunu bulur."""
    text_lower = text.lower()
    for category, keywords in KEYWORD_MAP.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category
    return None


# ===================== VERİ ÇEKME (FINNHUB) =====================
def _finnhub_quote(symbol: str):
    """Finnhub /quote endpoint."""
    url = "https://finnhub.io/api/v1/quote"
    params = {"symbol": symbol, "token": FINNHUB_API_KEY}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Finnhub istek hatası ({symbol}): {e}")
        return {}


def fetch_asset(symbol: str, name: str, is_crypto: bool = False):
    """Tek sembol için fiyat + değişim yüzdesi çeker."""
    data = _finnhub_quote(symbol)
    price = data.get("c")
    prev = data.get("pc")

    if price is None or price == 0:
        logger.warning(f"⚠️ {name} ({symbol}): fiyat 0/None döndü → {data}")
        return f"{name}: veri yok"

    change_pct = ((price - prev) / prev * 100) if (prev and prev != 0) else 0
    decimals = 2 if is_crypto else 4
    return f"{name}: {price:,.{decimals}f} (%{change_pct:+.2f})"


def fetch_forex(base: str, target: str, name: str):
    """Finnhub forex için 'OANDA:XXX_YYY' formatı kullanılır."""
    symbol = f"OANDA:{base}_{target}"
    data = _finnhub_quote(symbol)
    price = data.get("c")

    if price is None or price == 0:
        logger.warning(f"⚠️ {name} ({symbol}): fiyat 0/None → {data}")
        return f"{name}: veri yok"

    return f"{name}: {price:.4f}"


def fetch_emtia(symbol: str, name: str):
    return fetch_asset(symbol, name, is_crypto=False)


def update_all_caches():
    """Tüm kategorileri günceller."""
    logger.info("🔄 Veri güncelleme başladı...")
    
    # 1. Emtia
    try:
        cache_data["emtia"] = "\n".join([
            fetch_emtia("OANDA:XAU_USD", "Altın (ONS)"),
            fetch_emtia("OANDA:XAG_USD", "Gümüş (ONS)"),
            fetch_emtia("OANDA:BCO_USD", "Brent Petrol"),
        ])
    except Exception as e:
        logger.exception(f"Emtia güncelleme hatası: {e}")

    # 2. Kripto
    try:
        cache_data["kripto"] = "\n".join([
            fetch_asset("BINANCE:BTCUSDT", "Bitcoin", is_crypto=True),
            fetch_asset("BINANCE:ETHUSDT", "Ethereum", is_crypto=True),
        ])
    except Exception as e:
        logger.exception(f"Kripto güncelleme hatası: {e}")

    # 3. Döviz
    try:
        cache_data["doviz"] = "\n".join([
            fetch_forex("USD", "TRY", "Dolar"),
            fetch_forex("EUR", "TRY", "Euro"),
        ])
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
        [InlineKeyboardButton("💎 Destek Ol & İletişim", callback_data='destek')],
        [InlineKeyboardButton("⚠️ Yasal Uyarı", callback_data='uyari')],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_category(update: Update, category: str, edit: bool = False):
    """Belirtilen kategoriyi gönderir. edit=True ise mesajı düzenler."""
    if category == 'destek':
        text = cache_data.get('destek', "Destek metni yüklenemedi.")
        parse_mode = 'Markdown'
    else:
        text = cache_data.get(category, "Veri bulunamadı")
        footer = f"\n\nSon Güncelleme: {cache_data['last_update']}\n⚠️ Bilgi amaçlıdır."
        text = text + footer
        parse_mode = None

    if edit and update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=get_main_keyboard(),
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.warning(f"edit_message_text hatası: {e}")
            await update.callback_query.message.reply_text(
                text=text,
                reply_markup=get_main_keyboard(),
                parse_mode=parse_mode
            )
    else:
        await update.message.reply_text(
            text=text,
            reply_markup=get_main_keyboard(),
            parse_mode=parse_mode
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! Piyasa takip botuna hoş geldin.\n\n"
        "💡 **Akıllı Bot:** Aşağıdaki menüyü kullanabilir veya doğrudan "
        "\"dolar\", \"altın\", \"bitcoin\" gibi kelimeler yazabilirsin.",
        reply_markup=get_main_keyboard()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_category(update, query.data, edit=True)


async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcının yazdığı metni analiz eder ve akıllı yanıt verir."""
    user_text = update.message.text
    category = detect_category(user_text)

    if category:
        await send_category(update, category, edit=False)
    else:
        await update.message.reply_text(
            "🤔 Seni tam anlayamadım. Lütfen aşağıdaki menüden bir seçim yap "
            "veya \"dolar\", \"altın\", \"bitcoin\" gibi kelimeler yaz.",
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

    # İlk veri önbelleğini başlat
    threading.Thread(target=update_all_caches, daemon=True).start()

    # Zamanlayıcı başlat
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_all_caches, 'cron', minute='*/30')
    scheduler.start()
    logger.info("⏰ Scheduler başlatıldı (her 30 dakikada bir).")

    # Web/Health Server thread başlat
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask thread başlatıldı.")

    # Telegram Bot Polling
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
