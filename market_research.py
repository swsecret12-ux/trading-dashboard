import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timezone
import urllib.parse
import xml.etree.ElementTree as ET

# 💡 야후 차단(Rate limit) 우회를 위한 강력한 세션 위장
def get_robust_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    })
    return session

def fetch_investing_news(ticker):
    try:
        query = urllib.parse.quote(f"{ticker} stock OR partnership OR earnings")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news_items = []
        for item in root.findall('.//item')[:4]:
            title = item.find('title').text
            pubDate = item.find('pubDate').text
            news_items.append(f"- [{pubDate}] {title}")
        return "\n".join(news_items) if news_items else "관련 뉴스가 없습니다."
    except:
        return "뉴스 수집 실패"

def get_earnings_html_via_api(ticker):
    try:
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=earningsHistory,calendarEvents"
        session = get_robust_session()
        res = session.get(url, timeout=5)
        data = res.json()
        
        rows = []
        
        calendar = data.get('quoteSummary', {}).get('result', [{}])[0].get('calendarEvents', {}).get('earnings', {})
        earnings_dates = calendar.get('earningsDate', [])
        if earnings_dates:
            future_date = earnings_dates[0].get('fmt', '')
            if future_date:
                est = calendar.get('earningsAverage', {}).get('raw', '')
                rows.append(f"<tr style='background-color:#fffbea;'><td>⏳ {future_date} (예정)</td><td>{est if est else '-'}</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>")
        
        history = data.get('quoteSummary', {}).get('result', [{}])[0].get('earningsHistory', {}).get('history', [])
        for item in reversed(history):
            date_str = item.get('quarter', {}).get('fmt', '')
            if not date_str: continue
            
            eps_est = item.get('epsEstimate', {}).get('fmt', '-')
            eps_act = item.get('epsActual', {}).get('fmt', '-')
            surp = item.get('surprisePercent', {}).get('raw', '-')
            
            surp_html = "-"
            if isinstance(surp, (int, float)):
                color = "#22c55e" if surp > 0 else "#ef4444"
                surp_html = f"<span style='color:{color}; font-weight:bold;'>{surp*100:.1f}% {'상회' if surp > 0 else '하회'}</span>"
            
            rows.append(f"<tr><td>{date_str}</td><td>{eps_est}</td><td>{eps_act}</td><td>{surp_html}</td><td>-</td><td>-</td></tr>")
            
        if not rows: return "<p>실적 데이터가 없습니다.</p>"
            
        html = "<table class='ma-table'><tr><th>발표일(분기)</th><th>시장 예상치</th><th>실제 발표치</th><th>서프라이즈</th><th>종목 당일 등락</th><th>나스닥 당일 등락</th></tr>"
        html += "".join(rows) + "</table>"
        return html
    except Exception as e:
        return f"<p style='color:#ef4444;'>실적 데이터 일시 오류: JSON 파싱 실패 ({str(e)})</p>"

def fetch_financial_data(ticker_symbol):
    try:
        # 💡 야후 차단을 뚫기 위해 yfinance 내부 요청에도 커스텀 세션 강제 주입
        session = get_robust_session()
        ticker = yf.Ticker(ticker_symbol, session=session)
        info = ticker.info
        market_cap = info.get('marketCap', 0)
        
        df_1d = ticker.history(period="1y", interval="1d")
        df_1h = ticker.history(period="730d", interval="1h")
        
        if df_1d.empty or df_1h.empty:
            return {"error": "차트 데이터를 가져올 수 없습니다."}
            
        current_price = df_1d['Close'].iloc[-1]
        
        df_1d_ma = pd.DataFrame({'Close': df_1d['Close']})
        df_1d_ma['EMA200_1D'] = df_1d_ma['Close'].ewm(span=200, adjust=False).mean()
        
        df_4h_ma = df_1h.resample('4h').agg({'Close': 'last'}).dropna()
        df_4h_ma['EMA200_4H'] = df_4h_ma['Close'].ewm(span=200, adjust=False).mean()
        
        df_1d_ma.index = pd.to_datetime(df_1d_ma.index, utc=True)
        df_4h_ma.index = pd.to_datetime(df_4h_ma.index, utc=True)
        
        df_1d_ma = df_1d_ma[['EMA200_1D']].sort_index()
        df_4h_ma = df_4h_ma[['EMA200_4H', 'Close']].sort_index()
        
        merged = pd.merge_asof(df_4h_ma, df_1d_ma, left_index=True, right_index=True, direction='backward').dropna()
        merged['Prev_4H'] = merged['EMA200_4H'].shift(1)
        merged['Prev_1D'] = merged['EMA200_1D'].shift(1)
        
        gc = merged[(merged['EMA200_4H'] > merged['EMA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
        dc = merged[(merged['EMA200_4H'] < merged['EMA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])]
        
        last_cross_type = "최근 1년 내 크로스 없음"
        last_cross_date = "-"
        ma_html = "<p>최근 1년 내 4H/1D EMA 200 크로스가 없습니다.</p>"
        
        if not gc.empty or not dc.empty:
            last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize('UTC')
            last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize('UTC')
            latest_idx = max(last_gc, last_dc)
            
            cross_name = "🟢 골든크로스" if latest_idx == last_gc else "🔴 데드크로스"
            days_diff = (datetime.now(timezone.utc) - latest_idx).days
            if days_diff <= 90: cross_name = f"🔥 {cross_name}"
                
            last_cross_type = cross_name
            last_cross_date = latest_idx.strftime('%Y-%m-%d %H:%M')
            
            color = "#22c55e" if "골든" in cross_name else "#ef4444"
            ma_html = f"<ul><li><b>상태:</b> <span style='color:{color}; font-weight:bold;'>{cross_name}</span></li>"
            ma_html += f"<li><b>발생일:</b> {last_cross_date}</li>"
            ma_html += f"<li><b>당시 주가:</b> ${merged.loc[latest_idx, 'Close']:.2f}</li></ul>"
            
        ret_1m = ((current_price - df_1d['Close'].iloc[-21]) / df_1d['Close'].iloc[-21]) * 100 if len(df_1d) > 21 else 0
        ret_3m = ((current_price - df_1d['Close'].iloc[-63]) / df_1d['Close'].iloc[-63]) * 100 if len(df_1d) > 63 else 0
        
        momentum_html = f"<ul><li><b>현재가:</b> ${current_price:.2f}</li>"
        momentum_html += f"<li><b>1개월 변동:</b> {ret_1m:+.2f}%</li>"
        momentum_html += f"<li><b>3개월 변동:</b> {ret_3m:+.2f}%</li></ul>"
        
        earnings_html = get_earnings_html_via_api(ticker_symbol)
        
        try:
            news_items = ticker.news
            news_lines = []
            if news_items:
                for n in news_items[:10]:
                    title = n.get('title', '')
                    if not title: title = n.get('content', {}).get('title', '')
                    pub_time = n.get('providerPublishTime', 0)
                    date_str = pd.to_datetime(pub_time, unit='s').strftime('%Y-%m-%d') if pub_time else "날짜미상"
                    if title: news_lines.append(f"- [{date_str}] {title}")
            raw_news = "\n".join(news_lines) if news_lines else "최근 뉴스가 없습니다."
        except:
            raw_news = fetch_investing_news(ticker_symbol) # 야후 뉴스 실패 시 대체

        return {
            "market_cap": market_cap,
            "last_cross_type": last_cross_type,
            "last_cross_date": last_cross_date,
            "ma_html": ma_html,
            "momentum_html": momentum_html,
            "earnings_html": earnings_html,
            "raw_news": raw_news
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_issue, news_content):
    from api_utils import ask_gemini_dynamic
    today = datetime.now().strftime('%Y-%m-%d')
    prompt = f"""
    당신은 월스트리트 수석 애널리스트입니다. 아래 데이터를 바탕으로 투자 분석 보고서를 마크다운으로 작성하세요.
    [종목]: {ticker} (섹터: {sector}) | [기준일]: {today}
    
    [수집된 글로벌 뉴스]
    {fin_data.get('raw_news', '')}
    
    [🚨 핵심 지시사항]
    1. 뉴스에 명시되지 않았더라도 네 사전 지식을 동원해 최근 3개월간 이 종목을 움직인 '핵심 촉매제(예: 파트너십, M&A, 실적 등)'를 무조건 찾아내서 적으세요!
    2. 무조건 긍정적으로 포장하지 말고 리스크를 비판적으로 서술하세요.
    
    [보고서 필수 목차]
    1. 📊 시장 위치 및 핵심 밸류체인 요약
    2. 🚨 최근 급변동 사유 팩트체크 (구체적 호재/악재 및 파급력)
    3. 💰 실적 및 모멘텀 종합 의견
    4. 💡 기관 트레이딩 결론 (Actionable Insight)
    """
    return ask_gemini_dynamic(prompt, [])
