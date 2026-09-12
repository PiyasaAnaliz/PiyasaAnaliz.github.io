
import logging
from datetime import datetime
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

# 1. AYARLAR VE API ANAHTARLARI
TELEGRAM_TOKEN = "TELEGRAM_BOT_TOKEN_BURAYA"
FINNHUB_API_KEY = "FINNHUB_ANAHTARIN_BURAYA"

# Günlük limit yönetimi: Toplam 25 hak var.
DAY_REQUESTS = 15
NIGHT_REQUESTS = 10

# Veri Depoları (Cache)
cache_data = {
    "emitallar": "Veriler yükleniyor...",
    "kripto": "Veriler yükleniyor...",
    "bist": "Veriler yükleniyor...",
    "last_update": "Henüz güncellenmedi"
}

# Logger ayarı
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 2. VERİ ÇEKME FONKSİYONLARI (API İstekleri)
def fetch_metal_data():
    """Finnhub'dan emtia/metal verisi çeker"""
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol=OANDA:XAUUSD&token={FINNHUB_API_KEY}"
        response = requests.get(url).json()
        price = response.get('c', 'N/A')
        return f"Altın (ONS): ${price}"
    except Exception as e:
        logging.error(f"Emtia hatası: {e}")
        return "Emtia verisi şu an alınamıyor."

def fetch_crypto_data():
    """Kripto verisi çeker"""
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol=BINANCE:BTCUSDT&token={FINNHUB_API_KEY}"
        response = requests.get(url).json()
        price = response.get('c', 'N/A')
        return f"Bitcoin (BTC): ${price}"
    except Exception as e:
        logging.error(f"Kripto hatası: {e}")
        return "Kripto verisi şu an alınamıyor."

def fetch_bist_data():
    """BIST için statik/gecikmeli mesaj (Limit koruması)"""
    return "BIST100: Gün sonu kapanış verileri baz alınmıştır. Anlık işlem içermez."

# 3. ZAMANLAYICI (Scheduler) GÖREVLERİ
def scheduled_day_job():
    """Gündüz saatlerinde çalışacak görev"""
    logging.info("Gündüz güncellemesi çalışıyor...")
    update_all_caches()

def scheduled_night_job():
    """Gece saatlerinde çalışacak görev"""
    logging.info("Gece güncellemesi çalışıyor...")
    update_all_caches()

def update_all_caches():
    """Tüm verileri günceller ve zamanı kaydeder"""
    cache_data["emitallar"] = fetch_metal_data()
    cache_data["kripto"] = fetch_crypto_data()
    cache_data["bist"] = fetch_bist_data()
    cache_data["last_update"] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    logging.info("Tüm veriler güncellendi.")

# 4. TELEGRAM BOT KOMUTLARI VE BUTONLAR
def get_main_keyboard():
    """Ana menü butonlarını oluşturur"""
    keyboard = [
        [InlineKeyboardButton("Emtialar ve Metaller", callback_data='emitallar')],
        [InlineKeyboardButton("Kripto Paralar", callback_data='kripto')],
        [InlineKeyboardButton("Borsa İstanbul (BİST)", callback_data='bist')],
        [InlineKeyboardButton("Yasal Uyarı", callback_data='uyari')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /start komutu """
    welcome_text = (
        "Hoş geldiniz! Piyasa takip sistemine giriş yaptınız.\n"
        "Aşağıdaki menüden istediğiniz kategoriyi seçebilirsiniz."
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Butonlara basıldığında çalışır"""
    query = update.callback_query
    await query.answer()

    update_text = f"\n\n*(Son Güncelleme: {cache_data['last_update']})*"
    warning_footer = "\n\n⚠️ *Bilgi Amaçlıdır:* Yatırım tavsiyesi değildir. Sorumluluk kabul edilmez."

    if query.data == 'emitallar':
        await query.edit_message_text(text=cache_data["emitallar"] + update_text + warning_footer, parse_mode='Markdown', reply_markup=get_main_keyboard())
    elif query.data == 'kripto':
        await query.edit_message_text(text=cache_data["kripto"] + update_text + warning_footer, parse_mode='Markdown', reply_markup=get_main_keyboard())
    elif query.data == 'bist':
        await query.edit_message_text(text=cache_data["bist"] + update_text + warning_footer, parse_mode='Markdown', reply_markup=get_main_keyboard())
    elif query.data == 'uyari':
        warning_message = "Sistem tamamen bilgilendirme amaçlı çalışır. Sunulan verilerin doğruluğu garanti edilmez ve oluşabilecek maddi kayıplardan sistem sorumlu tutulamaz."
        await query.edit_message_text(text=warning_message, reply_markup=get_main_keyboard())

# 5. ANA PROGRAM BAŞLANGICI
if __name__ == '__main__':
    update_all_caches()

    scheduler = BackgroundScheduler()
    # Gündüz: 09:00 - 18:00 arası her saat başı
    scheduler.add_job(scheduled_day_job, 'cron', hour='9-18', minute=0)
    # Gece: 19:00 - 08:00 arası belirli saatlerde (Limit koruması)
    scheduler.add_job(scheduled_night_job, 'cron', hour='19,22,1,4,7', minute=0)
    scheduler.start()

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    logging.info("Bot çalışmaya başladı...")
    application.run_polling()
  
