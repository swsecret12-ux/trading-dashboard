import yfinance as yf
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse
import xml.etree.ElementTree as ET

def fetch_investing_news(ticker):
    """구글 뉴스 RSS를 우회하여 Investing.com의 최신 기사 3개를 긁어옵니다."""
    try:
        query = urllib.parse.quote(f"{ticker} stock site:investing.com")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news_items = []
        for item in root.findall('.//item')[:3]:
            title = item.find('title').text
            pubDate = item.find('pubDate').text
            news_items.append(f"- {title} ({pubDate})")
        return "\n".join(news_items) if news_items else "관련 Investing.com 뉴스가 없습니다."
    except:
        return "Investing.com 뉴스 수집 실패"

def fetch_saveticker_news(user_id, password):
    """SaveTicker 자동 로그인 및 최신 뉴스 크롤링"""
    if not user_id or not password:
        return "SaveTicker 계정 정보가 없습니다."
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        
        login_url = "https://www.saveticker.com/api/auth/callback/credentials"
        session.post(login_url, data={"email": user_id, "password": password}, timeout=10)
        
        res = session.get("https://www.saveticker.com/news", timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all(['p', 'article'])
        text = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
        
        if not text:
            return "SaveTicker 뉴스 본문 추출 실패 (봇 차단됨)"
        return f"[SaveTicker 요약]\n{text[:2500]}"
    except Exception as e:
        return f"SaveTicker 크롤링 에러: {str(e)}"

def fetch_financial_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        market_cap = info.get('marketCap', 0)
        if market_cap > 1e12: mcap_str = f"{market_cap / 1e12:.2f}T (조 달러)"
        elif market_cap > 1e9: mcap_str = f"{market_cap / 1e9:.2f}B (십억 달러)"
        elif market_cap > 1e6: mcap_str = f"{market_cap / 1e6:.2f}M (백만 달러)"
        else: mcap_str = "데이터 없음"

        # 일봉 데이터 로드
        hist_1d = ticker.history(period="2y")
        if hist_1d.empty: return {"error": "일봉 차트 데이터를 불러올 수 없습니다."}
        
        current_price = float(hist_1d['Close'].iloc[-1])
        current_vol = int(hist_1d['Volume'].iloc[-1])
        
        def calc_return(days):
            if len(hist_1d) > days:
                past = float(hist_1d['Close'].iloc[-(days+1)])
                pct = round(((current_price - past)/past)*100, 2)
                sign = "+" if pct > 0 else ""
                return f"${past:.2f} ➔ ${current_price:.2f} ({sign}{pct}%)"
            return "-"
        
        vol_1d = calc_return(1)
        vol_1w = calc_return(5)
        vol_1m = calc_return(20)
        vol_1q = calc_return(60)
        vol_1y = calc_return(250)

        # 1일봉 MA200 계산
        hist_1d['MA200_1D'] = hist_1d['Close'].rolling(window=200).mean()
        
        # 4시간봉 데이터 로드
        hist_1h = ticker.history(period="730d", interval="1h")
        if not hist_1h.empty:
            hist_4h = hist_1h.resample('4h').agg({'Close': 'last'}).dropna()
            hist_4h['MA200_4H'] = hist_4h['Close'].rolling(window=200).mean()
            
            # 타임존 일치화 및 4H vs 1D 크로스 분석
            if hist_1d.index.tz is None: hist_1d.index = hist_1d.index.tz_localize('UTC')
            if hist_4h.index.tz is None: hist_4h.index = hist_4h.index.tz_localize('UTC')
            
            df_1d_ma = hist_1d[['MA200_1D']].dropna().sort_index()
            df_4h_ma = hist_4h[['MA200_4H', 'Close']].dropna().sort_index()
            
            merged = pd.merge_asof(df_4h_ma, df_1d_ma, left_index=True, right_index=True, direction='backward')
            merged = merged.dropna()
            
            merged['Prev_4H'] = merged['MA200_4H'].shift(1)
            merged['Prev_1D'] = merged['MA200_1D'].shift(1)
            
            gc = merged[(merged['MA200_4H'] > merged['MA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
            dc = merged[(merged['MA200_4H'] < merged['MA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])]
            
            if not gc.empty or not dc.empty:
                last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize(merged.index.tz)
                last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize(merged.index.tz)
                
                latest_idx = max(last_gc, last_dc)
                cross_type = "🟢 골든크로스 (4H > 1D)" if latest_idx == last_gc else "🔴 데드크로스 (4H < 1D)"
                cross_date = latest_idx.strftime('%Y-%m-%d %H:%M')
                cross_price = f"${merged.loc[latest_idx, 'Close']:.2f}"
            else:
                cross_type, cross_date, cross_price = "크로스 발생 안함 (최근 1년)", "-", "-"
            
            curr_4h_ma200 = f"${merged['MA200_4H'].iloc[-1]:.2f}"
            curr_1d_ma200 = f"${merged['MA200_1D'].iloc[-1]:.2f}"
        else:
            cross_type, cross_date, cross_price = "4H 데이터 로드 불가", "-", "-"
            curr_4h_ma200 = "-"
            curr_1d_ma200 = f"${hist_1d['MA200_1D'].iloc[-1]:.2f}" if not pd.isna(hist_1d['MA200_1D'].iloc[-1]) else "-"

        # 실적 (Earnings) 데이터 로드
        earnings_html = ""
        try:
            edts = ticker.get_earnings_dates(limit=5)
            if edts is not None and not edts.empty:
                edts = edts.reset_index()
                edts['Date'] = edts['Earnings Date'].dt.strftime('%Y-%m-%d')
                edts_table = "<table class='ma-table'><tr><th>발표일</th><th>예상 EPS</th><th>실제 EPS</th></tr>"
                for _, row in edts.iterrows():
                    eps_est = f"{row['EPS Estimate']}" if pd.notna(row['EPS Estimate']) else "-"
                    eps_rep = f"{row['Reported EPS']}" if pd.notna(row['Reported EPS']) else "-"
                    edts_table += f"<tr><td>{row['Date']}</td><td>{eps_est}</td><td>{eps_rep}</td></tr>"
                edts_table += "</table>"
                earnings_html = edts_table
            else:
                earnings_html = "<p>최근 실적 데이터가 없습니다.</p>"
        except:
            earnings_html = "<p>실적 데이터를 불러올 수 없습니다.</p>"

        # 뉴스 조합
        news = ticker.news
        yh_news = "\n".join([f"- {n.get('title','')}" for n in news[:3]]) if news else ""
        inv_news = fetch_investing_news(ticker_symbol)
        raw_news = f"[Yahoo News]\n{yh_news}\n\n[Investing.com News]\n{inv_news}"

        # HTML 구성
        ma_html = f"""
        <table class="ma-table">
          <tr><th>지표</th><th>상태/가격</th><th>발생일</th></tr>
          <tr><td><b>최근 크로스</b></td><td>{cross_type}</td><td>{cross_date}</td></tr>
          <tr><td><b>크로스 당시 주가</b></td><td>{cross_price}</td><td>-</td></tr>
          <tr><td><b>현재 4H MA200</b></td><td>{curr_4h_ma200}</td><td>-</td></tr>
          <tr><td><b>현재 1D MA200</b></td><td>{curr_1d_ma200}</td><td>-</td></tr>
        </table>
        """
        
        mom_html = f"""
        <table class="ma-table">
          <tr><th>기간</th><th>과거 ➔ 현재 (변동률)</th></tr>
          <tr><td><b>1일</b></td><td>{vol_1d}</td></tr>
          <tr><td><b>1주일</b></td><td>{vol_1w}</td></tr>
          <tr><td><b>1개월</b></td><td>{vol_1m}</td></tr>
          <tr><td><b>1분기</b></td><td>{vol_1q}</td></tr>
          <tr><td><b>1년</b></td><td>{vol_1y}</td></tr>
        </table>
        """

        return {
            "market_cap": mcap_str, "raw_news": raw_news, "ma_html": ma_html, 
            "momentum_html": mom_html, "earnings_html": earnings_html,
            "current_price": current_price, "current_vol": current_vol
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input="", saveticker_text=""):
    from api_utils import ask_gemini_dynamic
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    # 💡 AI 앵무새 방지 강력 경고 프롬프트 탑재
    prompt = f"""
    당신은 월스트리트의 최정상급 기관 애널리스트입니다. 미사여구와 감정적인 표현은 배제하고, 오직 데이터와 팩트 기반의 건조한(Dry) 문체로 리포트를 작성하세요.
    보고서 작성 기준일: {today_str}

    [분석 대상 데이터]
    - 종목명: {ticker} (섹터: {sector})
    - 시가총액: {fin_data.get('market_cap')}
    - 최신 뉴스(Yahoo & Investing): {fin_data.get('raw_news')}
    - SaveTicker 등 외부 수집 뉴스: {saveticker_text}
    - 유저 메모: {user_input}
    
    [작성 지침 - 반드시 아래 목차를 따를 것]
    1. 📊 시장 위치 및 경쟁 시황
       - 이 종목이 글로벌 {sector} 섹터 내에서 시가총액 기준으로 어느 정도 위치에 있는지 파악하여 기재 (예: 글로벌 소프트웨어 1위).
       - 주요 경쟁사(Peers) 또는 연계된 밸류체인(공급망) 주식들의 시황 동향을 심층 분석.
    2. 📰 핵심 이슈 및 팩트체크 (뉴스 기반)
       - 제공된 뉴스 및 외부 수집 뉴스를 크로스체크하여 상승/하락의 트리거가 된 주요 실적 발표, 파트너십, 악재 등 팩트만 서술.
    3. 💡 트레이딩 결론 (Actionable Insight)
       - 펀더멘털과 뉴스를 종합하여 현재 포지션 진입(Long/Short/관망)에 대한 기계적이고 전문적인 조언.
       
    🚨 [절대 주의사항]: 가격 변동 수치(%), 이동평균선 가격, 실적 데이터 등은 이미 대시보드 화면 좌측 표에 예쁘게 표시됩니다. 따라서 당신의 답변 본문에 그 숫자들을 앵무새처럼 똑같이 나열하거나 절대 반복해서 쓰지 마세요. 오직 인사이트와 팩트 위주로만 작성하세요.
    """
    return ask_gemini_dynamic(prompt, [])
