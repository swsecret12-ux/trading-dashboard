import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timezone
import urllib.parse
import xml.etree.ElementTree as ET
import time

def get_robust_session():
    """야후 파이낸스 접속 차단을 완벽히 우회하기 위한 스텔스 세션 헤더"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    })
    return session

def fetch_investing_news(ticker):
    """야후 뉴스 차단 시 작동하는 대체 구글 뉴스 크롤러"""
    try:
        query = urllib.parse.quote(f"{ticker} stock OR partnership OR earnings")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news_items = []
        for item in root.findall('.//item')[:5]:
            title = item.find('title').text
            pubDate = item.find('pubDate').text
            news_items.append(f"- [{pubDate}] {title}")
        return "\n".join(news_items) if news_items else "관련 뉴스가 없습니다."
    except:
        return "뉴스 수집 실패"

def get_earnings_html_via_api(ticker):
    """lxml 에러 방어: 순수 JSON 서버에서 최근 4분기 실적과 주가 변동률까지 추출"""
    try:
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=earningsHistory,calendarEvents"
        session = get_robust_session()
        res = session.get(url, timeout=5)
        data = res.json()
        
        rows = []
        
        # 1. 미래 실적 (예정일)
        calendar = data.get('quoteSummary', {}).get('result', [{}])[0].get('calendarEvents', {}).get('earnings', {})
        earnings_dates = calendar.get('earningsDate', [])
        if earnings_dates:
            future_date = pd.to_datetime(earnings_dates[0].get('raw', 0), unit='s').strftime('%Y-%m-%d') if earnings_dates[0].get('raw') else ""
            if future_date and future_date != "1970-01-01":
                est = calendar.get('earningsAverage', {}).get('raw', '')
                rows.append(f"<tr style='background-color:#fffbea;'><td>⏳ {future_date} (예정)</td><td>{est if est else '-'}</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>")
        
        # 2. 과거 실적 히스토리
        history = data.get('quoteSummary', {}).get('result', [{}])[0].get('earningsHistory', {}).get('history', [])
        
        # 야후 차트 데이터 로드 (실적 발표일 당일 등락률 계산용)
        try:
            hist_df = yf.Ticker(ticker, session=session).history(period="2y")
            sp500_df = yf.Ticker("^GSPC", session=session).history(period="2y")
        except:
            hist_df = pd.DataFrame()
            sp500_df = pd.DataFrame()

        for item in reversed(history): 
            date_raw = item.get('quarter', {}).get('raw', 0)
            if not date_raw: continue
            
            date_obj = pd.to_datetime(date_raw, unit='s')
            date_str = date_obj.strftime('%Y-%m-%d')
            
            eps_est = item.get('epsEstimate', {}).get('fmt', '-')
            eps_act = item.get('epsActual', {}).get('fmt', '-')
            surp = item.get('surprisePercent', {}).get('raw', '-')
            
            surp_html = "-"
            if isinstance(surp, (int, float)):
                color = "#22c55e" if surp > 0 else "#ef4444"
                surp_html = f"<span style='color:{color}; font-weight:bold;'>{surp*100:.1f}% {'상회' if surp > 0 else '하회'}</span>"
            
            stock_change_html = "-"
            sp500_change_html = "-"
            
            if not hist_df.empty and not sp500_df.empty:
                closest_date = hist_df.index[hist_df.index <= date_obj.tz_localize('UTC')]
                if not closest_date.empty:
                    target_d = closest_date[-1]
                    try:
                        s_open = hist_df.loc[target_d, 'Open']
                        s_close = hist_df.loc[target_d, 'Close']
                        s_pct = ((s_close - s_open) / s_open) * 100
                        s_color = "#22c55e" if s_pct > 0 else "#ef4444"
                        stock_change_html = f"<span style='color:{s_color}; font-weight:bold;'>{s_pct:+.2f}%</span>"
                        
                        n_open = sp500_df.loc[target_d, 'Open']
                        n_close = sp500_df.loc[target_d, 'Close']
                        n_pct = ((n_close - n_open) / n_open) * 100
                        n_color = "#22c55e" if n_pct > 0 else "#ef4444"
                        sp500_change_html = f"<span style='color:{n_color}; font-weight:bold;'>{n_pct:+.2f}%</span>"
                    except: pass
            
            rows.append(f"<tr><td>{date_str}</td><td>{eps_est}</td><td>{eps_act}</td><td>{surp_html}</td><td>{stock_change_html}</td><td>{sp500_change_html}</td></tr>")
            
        if not rows: return "<p>실적 데이터를 불러올 수 없습니다.</p>"
            
        html = "<table class='ma-table'><tr><th>발표일(분기)</th><th>예상 EPS</th><th>실측 EPS</th><th>서프라이즈</th><th>종목 당일 등락</th><th>S&P 500 당일 등락</th></tr>"
        html += "".join(rows) + "</table>"
        return html
    except Exception as e:
        return f"<p style='color:#ef4444;'>실적 데이터 일시 오류: JSON 서버 파싱 실패 ({str(e)})</p>"

def fetch_financial_data(ticker_symbol):
    """야후 파이낸스 차단을 뚫기 위한 3중 자동 재시도 로직 탑재"""
    for attempt in range(3):
        try:
            session = get_robust_session()
            ticker = yf.Ticker(ticker_symbol, session=session)
            info = ticker.info
            market_cap = info.get('marketCap', 0)
            
            df_1d = ticker.history(period="1y", interval="1d")
            df_1h = ticker.history(period="730d", interval="1h")
            sp500_1d = yf.Ticker("^GSPC", session=session).history(period="1y", interval="1d")
            
            if df_1d.empty or df_1h.empty:
                return {"error": "차트 데이터를 가져올 수 없습니다."}
                
            current_price = df_1d['Close'].iloc[-1]
            
            # [이평선 3연속 크로스 추적 로직]
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
            
            gc = merged[(merged['EMA200_4H'] > merged['EMA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])].copy()
            dc = merged[(merged['EMA200_4H'] < merged['EMA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])].copy()
            
            gc['Type'] = "🟢 골든크로스"
            dc['Type'] = "🔴 데드크로스"
            crosses = pd.concat([gc, dc]).sort_index()
            
            if crosses.empty:
                ma_html = "<p>최근 1년 내 4H/1D EMA 200 크로스가 없습니다.</p>"
                last_cross_type = "크로스 없음"
                last_cross_date = "-"
            else:
                last_cross_type = crosses.iloc[-1]['Type']
                last_cross_date = crosses.index[-1].strftime('%Y-%m-%d %H:%M')
                
                ma_rows = []
                for idx, row in crosses.tail(3)[::-1].iterrows():
                    color = "#22c55e" if "골든" in row['Type'] else "#ef4444"
                    date_str = idx.strftime('%Y-%m-%d %H:%M')
                    price_str = f"${row['Close']:.2f}"
                    ma_rows.append(f"<tr><td><span style='color:{color}; font-weight:bold;'>{row['Type']}</span></td><td>{date_str}</td><td>{price_str}</td></tr>")
                    
                ma_html = "<table class='ma-table'><tr><th>상태 (최근 3회)</th><th>발생일</th><th>당시 주가</th></tr>"
                ma_html += "".join(ma_rows) + "</table>"
                
            # [모멘텀 정밀 비교 표]
            def get_ret(df, days):
                if len(df) > days: return ((df['Close'].iloc[-1] - df['Close'].iloc[-(days+1)]) / df['Close'].iloc[-(days+1)]) * 100
                return 0.0

            mom_rows = []
            periods = {"1일": 1, "1개월": 21, "3개월": 63, "6개월": 126, "1년": 252}
            for p_name, p_days in periods.items():
                s_ret = get_ret(df_1d, p_days)
                n_ret = get_ret(sp500_1d, p_days)
                s_col = "#22c55e" if s_ret > 0 else "#ef4444"
                n_col = "#22c55e" if n_ret > 0 else "#ef4444"
                mom_rows.append(f"<tr><td><b>{p_name} 변동</b></td><td><span style='color:{s_col}; font-weight:bold;'>{s_ret:+.2f}%</span></td><td><span style='color:{n_col}; font-weight:bold;'>{n_ret:+.2f}%</span></td></tr>")
                
            momentum_html = f"<table class='ma-table'><tr><th>기간</th><th>{ticker_symbol} 현재가: ${current_price:.2f}</th><th>S&P 500(^GSPC) 비교</th></tr>"
            momentum_html += "".join(mom_rows) + "</table>"
            
            earnings_html = get_earnings_html_via_api(ticker_symbol)
            
            try:
                news_items = ticker.news
                news_lines = []
                if news_items:
                    for n in news_items[:10]:
                        title = n.get('title', '')
                        if not title: title = n.get('content', {}).get('title', '')
                        pub_time = n.get('providerPublishTime', 0)
                        publisher = n.get('publisher', '알 수 없음')
                        date_str = pd.to_datetime(pub_time, unit='s').strftime('%Y-%m-%d') if pub_time else "날짜미상"
                        if title: news_lines.append(f"- [{date_str} / 출처: {publisher}] {title}")
                raw_news = "\n".join(news_lines) if news_lines else "최근 뉴스가 없습니다."
            except:
                raw_news = fetch_investing_news(ticker_symbol)

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
            if "429" in str(e) or "Too Many Requests" in str(e) or "Rate limited" in str(e):
                time.sleep(2) # 차단 시 2초 대기 후 재시도
                continue
            return {"error": str(e)}
            
    return {"error": "야후 파이낸스 데이터 수집 실패: Too Many Requests (IP 차단). 잠시 후 다시 시도해주세요."}

def analyze_sector_with_ai(ticker, sector, fin_data, user_issue, news_content):
    """AI에게 과거 핵심 팩트(파트너십 등)를 강제로 찾아오게 만드는 강력한 프롬프트"""
    from api_utils import ask_gemini_dynamic
    today = datetime.now().strftime('%Y-%m-%d')
    prompt = f"""
    당신은 월스트리트 수석 애널리스트입니다. 아래 데이터를 바탕으로 완벽한 투자 분석 보고서를 마크다운으로 작성하세요.
    
    [분석 대상]
    - 종목: {ticker} (섹터: {sector}) | 기준일: {today}
    - 최근 수집된 뉴스 (한계점: 최근 1주일치만 있음):
    {fin_data.get('raw_news', '')}
    - 나의 핵심 관점: {user_issue}
    
    [🚨 핵심 지시사항: 과거 팩트체크 초강제]
    1. 위 뉴스는 최근 며칠 치에 불과합니다. 따라서 최근 1년간 발생한 '30% 이상의 급등/급락' 등 결정적인 파동의 원인은 **당신의 사전 지식을 100% 동원하여 직접 찾아내야** 합니다! (예: 파트너십 발표, 어닝 서프라이즈, 가이던스 쇼크 등)
    2. 절대 "뉴스에 없다"거나 "알 수 없다"고 쓰지 마세요. 무조건 구체적인 촉매제를 표에 채워 넣으세요.
    3. 종합 의견 작성 시, 무조건 긍정적으로 포장하지 마세요. 밸류에이션 부담, 경쟁사 위협 등 **리스크 요인을 반드시 꼬집어 비판적으로 서술**하세요.
    
    [보고서 필수 목차 및 양식]
    
    ## 🏢 {ticker} 심층 분석 보고서 ({today} 기준)
    
    ### 1. 📊 시장 위치 및 핵심 밸류체인 요약
    
    ### 2. 🚨 최근 1년 10% 이상 급변동 사유 팩트체크 (가장 중요)
    | 발생 시점 (추정) | 변동 방향 | 구체적 촉매제 (당신의 지식 총동원) | 펀더멘털 파급력 |
    |---|---|---|---|
    | (예: 2024-05) | 상승/하락 | (예: MS/아마존 파트너십 등) | ... |
    
    ### 3. 💰 실적 및 모멘텀 종합 의견 (비판적 시각 필수 포함)
    
    ### 4. 💡 기관 트레이딩 결론 (Actionable Insight)
    - **현재 포지션:** (롱/숏/관망 중 택 1)
    - **핵심 리스크:**
    - **최종 Action:** 
    """
    return ask_gemini_dynamic(prompt, [])
