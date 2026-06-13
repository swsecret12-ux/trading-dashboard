import yfinance as yf
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse
import xml.etree.ElementTree as ET

def fetch_global_news(ticker):
    """구글 뉴스 RSS를 통해 해당 종목의 전 세계 최신 핵심 기사 5개를 긁어옵니다. (아마존 협업 등 캐치)"""
    try:
        query = urllib.parse.quote(f"{ticker} stock news OR partnership OR earnings")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news_items = []
        for item in root.findall('.//item')[:5]:
            title = item.find('title').text
            pubDate = item.find('pubDate').text
            news_items.append(f"- {title} ({pubDate})")
        return "\n".join(news_items) if news_items else "관련 글로벌 뉴스가 없습니다."
    except:
        return "글로벌 뉴스 수집 실패"

def fetch_saveticker_news(user_id, password):
    if not user_id or not password: return "SaveTicker 계정 없음"
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"})
        session.post("https://www.saveticker.com/api/auth/callback/credentials", data={"email": user_id, "password": password}, timeout=10)
        res = session.get("https://www.saveticker.com/news", timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all(['p', 'article'])
        text = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
        return f"[SaveTicker 요약]\n{text[:2000]}" if text else "SaveTicker 본문 추출 실패"
    except Exception as e: return f"SaveTicker 크롤링 에러: {str(e)}"

def fetch_financial_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # 1. 시가총액
        market_cap = info.get('marketCap', 0)
        if market_cap > 1e12: mcap_str = f"{market_cap / 1e12:.2f}T (조 달러)"
        elif market_cap > 1e9: mcap_str = f"{market_cap / 1e9:.2f}B (십억 달러)"
        elif market_cap > 1e6: mcap_str = f"{market_cap / 1e6:.2f}M (백만 달러)"
        else: mcap_str = "데이터 없음"

        # 2. 일봉 데이터 (과거 가격 및 변동성)
        hist_1d = ticker.history(period="2y")
        if hist_1d.empty: return {"error": "차트 데이터를 불러올 수 없습니다."}
        
        current_price = float(hist_1d['Close'].iloc[-1])
        current_vol = int(hist_1d['Volume'].iloc[-1])
        avg_vol_20d = int(hist_1d['Volume'].tail(20).mean())
        
        # 거래량 증가율 판독
        if current_vol > avg_vol_20d * 1.5: vol_status = f"🔥 급증 ({current_vol:,.0f}주)"
        else: vol_status = f"평이 ({current_vol:,.0f}주)"

        def calc_return(days):
            if len(hist_1d) > days:
                past = float(hist_1d['Close'].iloc[-(days+1)])
                pct = round(((current_price - past)/past)*100, 2)
                sign = "🔴" if pct < 0 else "🟢 +"
                return f"${past:.2f} ➔ ${current_price:.2f}<br><b>{sign}{pct}%</b>"
            return "-"
        
        vol_1d = calc_return(1)
        vol_1w = calc_return(5)
        vol_1m = calc_return(20)
        vol_1q = calc_return(60)
        vol_1y = calc_return(250)

        # 3. 4H / 1D 이평선 크로스 계산
        hist_1d['MA200_1D'] = hist_1d['Close'].rolling(window=200).mean()
        hist_1h = ticker.history(period="730d", interval="1h")
        if not hist_1h.empty:
            hist_4h = hist_1h.resample('4h').agg({'Close': 'last'}).dropna()
            hist_4h['MA200_4H'] = hist_4h['Close'].rolling(window=200).mean()
            if hist_1d.index.tz is None: hist_1d.index = hist_1d.index.tz_localize('UTC')
            if hist_4h.index.tz is None: hist_4h.index = hist_4h.index.tz_localize('UTC')
            
            df_1d_ma = hist_1d[['MA200_1D']].dropna().sort_index()
            df_4h_ma = hist_4h[['MA200_4H', 'Close']].dropna().sort_index()
            merged = pd.merge_asof(df_4h_ma, df_1d_ma, left_index=True, right_index=True, direction='backward').dropna()
            merged['Prev_4H'] = merged['MA200_4H'].shift(1)
            merged['Prev_1D'] = merged['MA200_1D'].shift(1)
            
            gc = merged[(merged['MA200_4H'] > merged['MA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
            dc = merged[(merged['MA200_4H'] < merged['MA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])]
            
            if not gc.empty or not dc.empty:
                last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize(merged.index.tz)
                last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize(merged.index.tz)
                latest_idx = max(last_gc, last_dc)
                cross_type = "🟢 4H/1D 골든크로스" if latest_idx == last_gc else "🔴 4H/1D 데드크로스"
                cross_date = latest_idx.strftime('%Y-%m-%d %H:%M')
                cross_price = f"${merged.loc[latest_idx, 'Close']:.2f}"
            else:
                cross_type, cross_date, cross_price = "최근 1년 내 발생 안함", "-", "-"
            curr_4h_ma200 = f"${merged['MA200_4H'].iloc[-1]:.2f}"
            curr_1d_ma200 = f"${merged['MA200_1D'].iloc[-1]:.2f}"
        else:
            cross_type, cross_date, cross_price, curr_4h_ma200 = "-", "-", "-", "-"
            curr_1d_ma200 = f"${hist_1d['MA200_1D'].iloc[-1]:.2f}" if not pd.isna(hist_1d['MA200_1D'].iloc[-1]) else "-"

        # 4. 실적 (Earnings) 직관적 포맷팅
        earnings_html = ""
        next_earnings = "미정"
        try:
            edts = ticker.get_earnings_dates(limit=10)
            if edts is not None and not edts.empty:
                edts = edts.reset_index()
                now = pd.Timestamp.now().tz_localize(edts['Earnings Date'].dt.tz)
                
                # 다음 실적 발표일 추출
                future_edts = edts[edts['Earnings Date'] > now].sort_values('Earnings Date')
                if not future_edts.empty: next_earnings = future_edts.iloc[0]['Earnings Date'].strftime('%Y년 %m월 %d일')
                
                # 과거 4분기 실적 추출
                past_edts = edts[edts['Earnings Date'] <= now].sort_values('Earnings Date', ascending=False).head(4)
                
                edts_table = f"<p><b>🗓️ 다음 실적 발표 예정일:</b> <span style='color:#d97706; font-weight:bold;'>{next_earnings}</span></p>"
                edts_table += "<table class='ma-table'><tr><th>분기 발표일</th><th>예상 EPS</th><th>실제 EPS</th><th>결과 (Surprise)</th></tr>"
                
                ai_earnings_data = [] # AI에게 넘겨줄 실적 요약
                for _, row in past_edts.iterrows():
                    date_str = row['Earnings Date'].strftime('%Y-%m-%d')
                    eps_est = row['EPS Estimate']
                    eps_rep = row['Reported EPS']
                    
                    if pd.notna(eps_est) and pd.notna(eps_rep) and eps_est != 0:
                        surp_pct = ((eps_rep - eps_est) / abs(eps_est)) * 100
                        if surp_pct > 0: res_str = f"<span style='color:green; font-weight:bold;'>🟢 +{surp_pct:.1f}% 상회</span>"
                        else: res_str = f"<span style='color:red; font-weight:bold;'>🔴 {surp_pct:.1f}% 하회</span>"
                        ai_earnings_data.append(f"[{date_str}] 예상 {eps_est} vs 실제 {eps_rep} ({surp_pct:.1f}%)")
                    else:
                        eps_est = "-" if pd.isna(eps_est) else f"${eps_est:.2f}"
                        eps_rep = "-" if pd.isna(eps_rep) else f"${eps_rep:.2f}"
                        res_str = "-"
                        
                    edts_table += f"<tr><td>{date_str}</td><td>${eps_est:.2f} if isinstance(eps_est, float) else eps_est}</td><td>${eps_rep:.2f} if isinstance(eps_rep, float) else eps_rep}</td><td>{res_str}</td></tr>"
                edts_table += "</table>"
                earnings_html = edts_table
                earnings_raw = " | ".join(ai_earnings_data)
            else:
                earnings_html = "<p>최근 실적 데이터가 없습니다.</p>"
                earnings_raw = "실적 데이터 없음"
        except Exception as e:
            earnings_html = f"<p>실적 파싱 에러: {str(e)}</p>"
            earnings_raw = "실적 파싱 에러"

        # 5. 글로벌 뉴스 스크래핑
        global_news = fetch_global_news(ticker_symbol)

        return {
            "market_cap": mcap_str, "global_news": global_news, "earnings_html": earnings_html,
            "earnings_raw": earnings_raw, "current_price": current_price, "vol_status": vol_status,
            "vol_1d": vol_1d, "vol_1w": vol_1w, "vol_1m": vol_1m, "vol_1q": vol_1q, "vol_1y": vol_1y,
            "cross_type": cross_type, "cross_date": cross_date, "cross_price": cross_price,
            "curr_4h_ma200": curr_4h_ma200, "curr_1d_ma200": curr_1d_ma200
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input="", saveticker_text=""):
    from api_utils import ask_gemini_dynamic
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    prompt = f"""
    당신은 월스트리트의 최정상급 기관 애널리스트입니다. 아래 데이터를 바탕으로 직관적이고 팩트 위주의 리포트를 작성하세요.
    보고서 작성 기준일: {today_str}

    [분석 대상 데이터]
    - 종목명: {ticker} (섹터: {sector})
    - 시가총액: {fin_data.get('market_cap')}
    - 현재가: ${fin_data.get('current_price', 0):.2f} / 거래량 동향: {fin_data.get('vol_status')}
    - 최근 4분기 실적 성과(Surprise): {fin_data.get('earnings_raw')}
    - 구글 뉴스(파트너십/M&A 등 핵심 팩트): {fin_data.get('global_news')}
    - SaveTicker 등 수집 팩트: {saveticker_text}
    - 사용자 메모: {user_input}
    
    [작성 지침 - 반드시 아래 목차를 따를 것]
    1. 💰 실적(Earnings) 종합 의견
       - 최근 4분기 EPS 상회/하회 추이를 바탕으로 기업의 펀더멘털 건전성을 직관적으로 요약.
    2. 📊 시장 위치 및 밸류체인(연관 주식)
       - {sector} 섹터 내에서 시총 기준 현재 위치(예: 글로벌 1위, 도전자 등) 명시.
       - 이 주식과 가격이 연동되는 주요 밸류체인 주식(경쟁사 또는 납품사) 2~3곳 언급.
    3. 📰 핵심 이슈 및 팩트체크 (뉴스 기반)
       - 구글 뉴스 및 수집된 뉴스에서 상승/하락을 유발한 '아마존 파트너십', 'M&A', '실적 발표' 등의 핵심 트리거 팩트만 서술. (절대 모호하게 적지 말 것)
    4. 💡 트레이딩 결론 (Actionable Insight)
       - 실적, 뉴스, 거래량을 종합하여 현재 포지션 진입(Long/Short/관망)에 대한 기관급 조언.
       
    🚨 주의사항: 좌측 대시보드에 이미 퍼센트(%)와 이동평균선 수치가 나오므로 본문에서 숫자를 앵무새처럼 나열하지 말고 '인사이트' 위주로 적으세요.
    """
    return ask_gemini_dynamic(prompt, [])
