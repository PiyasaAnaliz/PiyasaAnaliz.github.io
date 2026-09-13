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

# ===================== LOG AYARLARI =====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== AYARLAR =====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
if not TELEGRAM_TOKEN:
    raise SystemExit("❌ TELEGRAM_TOKEN eksik! Ortam değişkeni olarak tanımla.")

# ===================== DESTEK METNİ =====================
DESTEK_METNI = (
    "💎 *Bize Destek Olun & İletişim* 💎\n\n"
    "Merhaba! YouTube Katıl Butonu, Videonun Altındaki Süper Teşekkür ve "
    "Patreon üzerinden kanalımıza destek olabilirsiniz.\n\n"
    "🔗 *Kartvizit:* https://piyasaanaliz.github.io\n"
    "▶️ *YouTube:* https://www.youtube.com/@PiyasaAnalizim\n"
    "🎵 *TikTok:* https://www.tiktok.com/@piyasaanalizim\n"
    "📧 *İletişim:* MutinousTube@gmail.com\n\n"
    "⚠️ *YASAL UYARI*\n"
    "BİLGİ AMAÇLI YAPILAN PAYLAŞIMLAR YATIRIM DANIŞMANLIĞI KAPSAMINDA DEĞİLDİR."
)

# ===================== ÖNBELLEK =====================
cache_data = {
    "doviz": "Veriler yükleniyor...",
    "emtia": "Veriler yükleniyor...",
    "kripto": "Veriler yükleniyor...",
    "bist": "Veriler yükleniyor...",
    "uyari": (
        "⚠️ YASAL UYARI\n\n"
        "Bu botta yer alan tüm veriler yalnızca bilgilendirme amaçlıdır.\n"
        "Yatırım tavsiyesi değildir.\n\n"
        "BİLGİ AMAÇLI YAPILAN PAYLAŞIMLAR YATIRIM DANIŞMANLIĞI KAPSAMINDA DEĞİLDİR."
    ),
    "destek": DESTEK_METNI,
    "last_update": "Henüz güncellenmedi"
}

# ===================== AKILLI ALGILAMA =====================
KEYWORD_MAP = {
    "doviz": ["dolar", "usd", "euro", "eur", "döviz", "doviz", "kur", "sterlin", "gbp", "tl"],
    "emtia": ["altın", "altin", "gold", "gümüş", "gumus", "silver", "petrol", "brent", "emtia", "ons"],
    "kripto": ["bitcoin", "btc", "ethereum", "eth", "kripto", "crypto", "coin", "usdt", "solana", "sol"],
    "bist": ["bist", "borsa", "hisse", "endeks", "bist100", "xu100"],
    "destek": ["destek", "iletişim", "iletisim", "sosyal", "youtube", "patreon", "kanal"],
    "uyari": ["uyarı", "uyari", "yasal", "risk", "sorumluluk"]
}

def detect_category(text: str):
    text_lower = text.lower()
    for category, keywords in KEYWORD_MAP.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category
    return None

# ===================== VERİ ÇEKME (YFINANCE) =====================
def fetch_yfinance(symbol, name):
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")  # 5 günlük veri çek, daha stabil
        if hist.empty or len(hist) < 2:
            return f"{name}: veri yok"
        
        current_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-2]
        change_pct = ((current_price - prev_price) / prev_price * 100) if prev_price != 0 else 0
        
        decimals = 2 if current_price > 100 else 4
        return f"{name}: {current_price:,.{decimals}f} (%{change_pct:+.2f})"
    except Exception as e:
        logger.error(f"yfinance hatası ({symbol}): {e}")
        return f"{name}: veri yok"

def update_all_caches():
    logger.info("🔄 Veri güncelleme başladı...")
    
    try:
        cache_data["doviz"] = "\n".join([
            fetch_yfinance("USDTRY=X", "Dolar"),
            fetch_yfinance("EURTRY=X", "Euro"),
            fetch_yfinance("GBPTRY=X", "Sterlin"),
        ])
    except Exception as e:
        logger.exception(f"Döviz güncelleme hatası: {e}")

    try:
        cache_data["emtia"] = "\n".join([
            fetch_yfinance("GC=F", "Altın (ONS)"),
            fetch_yfinance("SI=F", "Gümüş (ONS)"),
            fetch_yfinance("BZ=F", "Brent Petrol"),
        ])
    except Exception as e:
        logger.exception(f"Emtia güncelleme hatası: {e}")

    try:
        cache_data["kripto"] = "\n".join([
            fetch_yfinance("BTC-USD", "Bitcoin"),
            fetch_yfinance("ETH-USD", "Ethereum"),
        ])
    except Exception as e:
        logger.exception(f"Kripto güncelleme hatası: {e}")

    try:
        cache_data["bist"] = fetch_yfinance("XU100.IS", "BIST100")
    except Exception as e:
        logger.exception(f"BIST güncelleme hatası: {e}")

    cache_data["last_update"] = datetime.now().strftime("%d-%m-%Y %H:%M")
    logger.info("✅ Tüm veriler güncellendi.")

# ===================== TELEGRAM KLAVYE =====================
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("💵 Dolar", callback_data='doviz')],
        [InlineKeyboardButton("💶 Euro", callback_data='doviz')],
        [InlineKeyboardButton("🥇 Altın", callback_data='emtia')],
        [InlineKeyboardButton("🪙 Kripto Paralar", callback_data='kripto')],
        [InlineKeyboardButton("📈 Borsa (BIST100)", callback_data='bist')],
        [InlineKeyboardButton("💎 Destek & İletişim", callback_data='destek')],
        [InlineKeyboardButton("⚠️ Yasal Uyarı", callback_data='uyari')],
    ]
    return InlineKeyboardMarkup(keyboard)

# ===================== MESAJ GÖNDERME =====================
async def send_category(update: Update, category: str, edit: bool = False):
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

# ===================== KOMUTLAR =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! Piyasa takip botuna hoş geldin.\n\n"
        "💡 Aşağıdaki menüden seçim yapabilir veya doğrudan "
        "\"dolar\", \"altın\", \"borsa\" gibi kelimeler yazabilirsin.",
        reply_markup=get_main_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_category(update, query.data, edit=True)

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    category = detect_category(user_text)
    if category:
        await send_category(update, category, edit=False)
    else:
        await update.message.reply_text(
            "🤔 Seni tam anlayamadım. Lütfen aşağıdaki menüden bir seçim yap "
            "veya \"dolar\", \"altın\", \"borsa\" gibi kelimeler yaz.",
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
def main():
    logger.info("🚀 Bot başlatılıyor...")
    threading.Thread(target=update_all_caches, daemon=True).start()

    scheduler = BackgroundScheduler()
    scheduler.add_job(update_all_caches, 'cron', minute='*/30')
    scheduler.start()
    logger.info("⏰ Scheduler başlatıldı.")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask thread başlatıldı.")

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
