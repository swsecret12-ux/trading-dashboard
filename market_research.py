import yfinance as yf
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse
import xml.etree.ElementTree as ET

def fetch_investing_news(ticker):
    try:
        query = urllib.parse.quote(f"{ticker} stock site:investing.com")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news_items = [f"- {item.find('title').text} ({item.find('pubDate').text})" for item in root.findall('.//item')[:3]]
        return "\n".join(news_items) if news_items else "관련 Investing.com 뉴스가 없습니다."
    except: return "Investing.com 뉴스 수집 실패"

def fetch_saveticker_news(user_id, password):
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        session.post("https://www.saveticker.com/api/auth/callback/credentials", data={"email": user_id, "password": password}, timeout=10)
        res = session.get("https://www.saveticker.com/news", timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all(['p', 'article', 'h1'])
        text = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
        return f"[SaveTicker 자동 수집]\n{text[:2500]}" if text else "뉴스 추출 실패"
    except Exception as e: return f"크롤링 에러: {str(e)}"

def fetch_financial_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        market_cap = info.get('marketCap', 0)
        mcap_str = f"{market_cap / 1e12:.2f}T" if market_cap > 1e12 else (f"{market_cap / 1e9:.2f}B" if market_cap > 1e9 else "데이터 없음")
        
        hist = ticker.history(period="2y")
        if hist.empty: return {"error": "데이터 로드 실패"}
        
        current_price = float(hist['Close'].iloc[-1])
        current_vol = int(hist['Volume'].iloc[-1])
        
        def calc_return(days):
            if len(hist) > days:
                past = float(hist['Close'].iloc[-(days+1)])
                pct = round(((current_price - past)/past)*100, 2)
                return f"${past:.2f} ➔ ${current_price:.2f} ({'+' if pct > 0 else ''}{pct}%)"
            return "-"
        
        hist['MA200_1D'] = hist['Close'].rolling(window=200).mean()
        hist_1h = ticker.history(period="730d", interval="1h")
        hist_4h = hist_1h.resample('4h').agg({'Close': 'last'}).dropna()
        hist_4h['MA200_4H'] = hist_4h['Close'].rolling(window=200).mean()
        
        # 크로스 계산
        if hist.index.tz is None: hist.index = hist.index.tz_localize('UTC')
        if hist_4h.index.tz is None: hist_4h.index = hist_4h.index.tz_localize('UTC')
        merged = pd.merge_asof(hist_4h[['MA200_4H', 'Close']], hist[['MA200_1D']].dropna(), left_index=True, right_index=True).dropna()
        merged['Prev_4H'] = merged['MA200_4H'].shift(1)
        merged['Prev_1D'] = merged['MA200_1D'].shift(1)
        
        gc = merged[(merged['MA200_4H'] > merged['MA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
        last_cross = "🟢 골든크로스" if not gc.empty else "🔴 데드크로스"
        
        return {
            "market_cap": mcap_str, "current_price": current_price, "current_vol": current_vol,
            "ma50": float(hist['MA50'].iloc[-1]) if 'MA50' in hist else 0,
            "ma200": float(hist['MA200'].iloc[-1]),
            "last_cross_type": last_cross,
            "vol_1d": calc_return(1), "vol_1w": calc_return(5), "vol_1m": calc_return(20),
            "vol_1q": calc_return(60), "vol_1y": calc_return(250),
            "raw_news": fetch_investing_news(ticker_symbol)
        }
    except Exception as e: return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input="", saveticker_text=""):
    from api_utils import ask_gemini_dynamic
    prompt = f"""
    당신은 월스트리트 기관 애널리스트입니다. 아래 데이터를 분석하여 건조한 팩트 중심의 리포트를 작성하세요.
    (종목: {ticker}, 섹터: {sector})
    데이터: 시총 {fin_data.get('market_cap')}, 이평선 현황: {fin_data.get('last_cross_type')}, 최근뉴스: {fin_data.get('raw_news')}
    [작성지침]
    1. 숫자를 앵무새처럼 반복하지 마세요. (이미 표에 다 있습니다.)
    2. 해당 섹터 내 시총 순위와 경쟁사를 분석하세요.
    3. 오직 팩트 기반의 트레이딩 인사이트만 간결하게 기술하세요.
    """
    return ask_gemini_dynamic(prompt, [])
