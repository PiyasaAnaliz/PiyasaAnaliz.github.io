import logging
from datetime import datetime
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

# ===================== AYARLAR =====================
TOKEN = "8730070682:AAEtuRaWhYt3gZHSCQoePxK_SmYlfheyAuk"

# ===================== VERİ ÇEKME =====================
def get_price(symbol, name):
    try:
        url = f"https://biquote.io/api/{symbol}"
        data = requests.get(url, timeout=10).json()
        price = data.get('mid', 0)
        change = data.get('dayDiffPercent', 0)
        return f"{name}: {price:.2f} (%{change:+.2f})"
    except:
        return f"{name} verisi alınamadı."

# ===================== KOMUTLAR =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Emtialar", callback_data='emtia')],
        [InlineKeyboardButton("Kripto Paralar", callback_data='kripto')],
        [InlineKeyboardButton("Döviz Kurları", callback_data='doviz')]
    ]
    
    await update.message.reply_text(
        "Merhaba! Piyasa fiyatlarını takip etmek için butonları kullanabilirsin.\n"
        "Ya da direkt **dolar**, **altın**, **bitcoin** yazabilirsin.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "emtia":
        text = get_price("XAUUSD", "Altın (ONS)")
    elif query.data == "kripto":
        text = get_price("BTCUSD", "Bitcoin")
    elif query.data == "doviz":
        text = f"{get_price('USDTRY', 'Dolar')}\n{get_price('EURTRY', 'Euro')}"
    else:
        text = "Veri bulunamadı."
    
    await query.edit_message_text(text=text, reply_markup=query.message.reply_markup)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    
    if "dolar" in text or "usd" in text:
        cevap = get_price("USDTRY", "Dolar")
    elif "euro" in text or "eur" in text:
        cevap = get_price("EURTRY", "Euro")
    elif "altın" in text or "gold" in text:
        cevap = get_price("XAUUSD", "Altın (ONS)")
    elif "bitcoin" in text or "btc" in text:
        cevap = get_price("BTCUSD", "Bitcoin")
    else:
        cevap = "Anlamadım. Dolar, Euro, Altın veya Bitcoin yazabilirsin."
    
    await update.message.reply_text(cevap)

# ===================== BAŞLAT =====================
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("Bot çalışıyor...")
    app.run_polling()
