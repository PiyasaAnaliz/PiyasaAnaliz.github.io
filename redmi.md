import os
import logging
from datetime import datetime
import yfinance as yf

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

COMMODITIES = {
    "Altın": "GC=F",
    "Gümüş": "SI=F",
    "Bakır": "HG=F",
    "Ham Petrol": "CL=F"
}

EXCHANGES = {
    "Dolar/TL": "USDTRY=X",
    "Euro/TL": "EURTRY=X",
    "Euro/Dolar": "EURUSD=X"
}

WORLD_INDICES = {
    "Dow Jones": "^DJI",
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "BIST 100": "XU100.IS"
}

def fetch_data(symbols_dict):
    rows = []
    for name, ticker_symbol in symbols_dict.items():
        try:
            ticker = yf.Ticker(ticker_symbol)
            price = ticker.fast_info.get('last_price')
            if price:
                rows.append(f"| **{name}** | `{ticker_symbol}` | `{round(price, 2)}` |")
            else:
                rows.append(f"| **{name}** | `{ticker_symbol}` | N/A |")
        except Exception as e:
            logging.error(f"{name} verisi alınamadı: {e}")
            rows.append(f"| **{name}** | `{ticker_symbol}` | Hata |")
    return rows

def generate_markdown():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    md_content = "<!-- MARKET_DATA_START -->\n"
    md_content += "### 📈 Canlı Piyasa Analiz Paneli\n"
    md_content += f"*Son Güncelleme: `{now}`*\n\n"
    
    md_content += "#### 💰 Değerli Madenler & Emtialar\n"
    md_content += "| Varlık | Sembol | Fiyat |\n| :--- | :--- | :--- |\n"
    md_content += "\n".join(fetch_data(COMMODITIES)) + "\n\n"
    
    md_content += "#### 💱 Döviz Kurları\n"
    md_content += "| Çift | Sembol | Oran |\n| :--- | :--- | :--- |\n"
    md_content += "\n".join(fetch_data(EXCHANGES)) + "\n\n"
    
    md_content += "#### 📊 Borsa Endeksleri\n"
    md_content += "| Endeks | Sembol | Değer |\n| :--- | :--- | :--- |\n"
    md_content += "\n".join(fetch_data(WORLD_INDICES)) + "\n"
    md_content += "<!-- MARKET_DATA_END -->"
    
    return md_content

def update_readme():
    readme_path = "README.md"
    
    # README dosyası yoksa varsayılan etiketlerle oluştur
    if not os.path.exists(readme_path):
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("<!-- MARKET_DATA_START -->\n<!-- MARKET_DATA_END -->")
            
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    start_marker = "<!-- MARKET_DATA_START -->"
    end_marker = "<!-- MARKET_DATA_END -->"

    # Etiketler varsa arasını değiştir, yoksa en alta ekle
    if start_marker in content and end_marker in content:
        before = content.split(start_marker)[0]
        after = content.split(end_marker)[1]
        new_content = before + generate_markdown() + after
    else:
        new_content = content + "\n\n" + generate_markdown()

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    logging.info("README.md başarıyla güncellendi.")

if __name__ == "__main__":
    update_readme()
