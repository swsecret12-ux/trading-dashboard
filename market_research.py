import pandas as pd
import requests
from datetime import datetime, timezone
import urllib.parse
import xml.etree.ElementTree as ET
import time
import random
import yfinance as yf

def get_robust_session():
    """야후 파이낸스 접속 차단을 완벽히 우회하기 위한 스텔스 세션 헤더 및 토큰 획득"""
    session = requests.Session()
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
    ]
    session.headers.update({
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive"
    })
    
    crumb = ""
    try:
        session.get("https://finance.yahoo.com/quote/AAPL", timeout=5)
        time.sleep(0.5)
        res = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=5)
        if res.status_code == 200: crumb = res.text.strip()
    except: pass
        
    return session, crumb

def get_yahoo_chart(ticker, r, i, session, crumb=""):
    """야후 내부 v8 API 다이렉트 통신 (IP 차단 방어)"""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?range={r}&interval={i}"
    if crumb: url += f"&crumb={crumb}"
    try:
        res = session.get(url, timeout=7)
        if res.status_code != 200: return pd.DataFrame()
        data = res.json()
        if not data.get('chart', {}).get('result'): return pd.DataFrame()
        result = data['chart']['result'][0]
        timestamps = result.get('timestamp', [])
        if not timestamps: return pd.DataFrame()
        quote = result.get('indicators', {}).get('quote', [{}])[0]
        df = pd.DataFrame({'Open': quote.get('open', []), 'Close': quote.get('close', [])}, index=pd.to_datetime(timestamps, unit='s', utc=True))
        return df.dropna()
    except: return pd.DataFrame()

def fetch_investing_news(ticker):
    """야후 뉴스 429 차단을 우회하기 위한 구글 뉴스 RSS 크롤러"""
    try:
        query = urllib.parse.quote(f"{ticker} stock OR earnings")
        url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news_items = []
        for item in root.findall('.//item')[:7]:
            title = item.find('title').text
            pubDate = item.find('pubDate').text
            try:
                dt = datetime.strptime(pubDate, "%a, %d %b %Y %H:%M:%S %Z")
                pubDate_str = dt.strftime("%Y-%m-%d")
            except: pubDate_str = pubDate
            news_items.append(f"- [{pubDate_str}] {title}")
        return "\n".join(news_items) if news_items else "최근 구글 검색 뉴스가 없습니다."
    except: return "뉴스 수집 실패 (Google RSS 우회 실패)"

def get_market_cap_and_earnings(ticker, session, crumb, hist_df, sp500_df, is_korean, benchmark_name):
    """yfinance 캘린더 엔진 활용: 완벽한 텍스트 날짜(Timezone 충돌 방어) 변환 및 익일(다음날) 주가 변동률 계산"""
    market_cap = 0
    earnings_html = ""
    rows = []
    upcoming_row = ""

    try:
        tkr = yf.Ticker(ticker)
        market_cap = tkr.info.get('marketCap', 0)
    except: pass

    # Timezone 문제를 막기 위해 차트 날짜를 문자열로 완벽 변환
    hist_dates = []
    if not hist_df.empty:
        hist_dates = hist_df.index.strftime('%Y-%m-%d').tolist()

    sp500_dates = []
    if not sp500_df.empty:
        sp500_dates = sp500_df.index.strftime('%Y-%m-%d').tolist()

    try:
        earn_df = tkr.get_earnings_dates(limit=8)
        if earn_df is not None and not earn_df.empty:
            
            now_tz = pd.Timestamp.now(tz=earn_df.index.tz)

            for idx_date, row in earn_df.iterrows():
                date_str = idx_date.strftime('%Y-%m-%d')
                eps_est = row.get('EPS Estimate', pd.NA)
                eps_act = row.get('Reported EPS', pd.NA)
                surp = row.get('Surprise(%)', pd.NA)

                # 💡 다가오는 미래 날짜는 가장 윗줄에 노란색으로 고정!
                if idx_date > now_tz and pd.isna(eps_act):
                    if not upcoming_row:
                        est_str = f"{eps_est:.2f}" if pd.notna(eps_est) else "-"
                        upcoming_row = f"<tr style='background-color:#fffbea;'><td>⏳ {date_str} (예정)</td><td>{est_str}</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>"
                    continue

                if pd.isna(eps_act) and pd.isna(eps_est): continue 

                est_str = f"{eps_est:.2f}" if pd.notna(eps_est) else "-"
                act_str = f"{eps_act:.2f}" if pd.notna(eps_act) else "-"

                surp_html = "-"
                if pd.notna(surp):
                    surp_val = surp * 100
                    color = "#22c55e" if surp_val > 0 else "#ef4444"
                    surp_html = f"<span style='color:{color}; font-weight:bold;'>{surp_val:+.1f}% {'상회' if surp_val > 0 else '하회'}</span>"

                stock_change_html = "-"
                sp500_change_html = "-"

                # 💡 핵심 로직: 발표 당일 종가 vs "다음 거래일 종가" 비교 (실적 발표 후 익일 반영분)
                if date_str in hist_dates:
                    idx_pos = hist_dates.index(date_str)
                    
                    if idx_pos + 1 < len(hist_df):
                        prev_close = hist_df['Close'].iloc[idx_pos]      # 당일 종가
                        next_close = hist_df['Close'].iloc[idx_pos + 1]  # 익일 종가
                        s_pct = ((next_close - prev_close) / prev_close) * 100
                        s_color = "#22c55e" if s_pct > 0 else "#ef4444"
                        stock_change_html = f"<span style='color:{s_color}; font-weight:bold;'>{s_pct:+.2f}%</span>"

                        next_date_str = hist_dates[idx_pos + 1]
                        if next_date_str in sp500_dates:
                            n_idx_pos = sp500_dates.index(next_date_str)
                            if n_idx_pos - 1 >= 0:
                                n_prev_close = sp500_df['Close'].iloc[n_idx_pos - 1]
                                n_next_close = sp500_df['Close'].iloc[n_idx_pos]
                                n_pct = ((n_next_close - n_prev_close) / n_prev_close) * 100
                                n_color = "#22c55e" if n_pct > 0 else "#ef4444"
                                sp500_change_html = f"<span style='color:{n_color}; font-weight:bold;'>{n_pct:+.2f}%</span>"

                rows.append(f"<tr><td>{date_str}</td><td>{est_str}</td><td>{act_str}</td><td>{surp_html}</td><td>{stock_change_html}</td><td>{sp500_change_html}</td></tr>")
    except Exception as e: pass

    final_rows = []
    if upcoming_row: final_rows.append(upcoming_row)
    final_rows.extend(rows)

    if final_rows:
        earnings_html = f"<table class='ma-table'><tr><th>발표일(분기)</th><th>예상 EPS</th><th>실측 EPS</th><th>서프라이즈</th><th>종목 익일 등락</th><th>{benchmark_name} 익일 등락</th></tr>"
        earnings_html += "".join(final_rows) + "</table>"
        earnings_html += "<p style='font-size: 0.85rem; color: #666; margin-top: 5px;'>* 실적 데이터 출처: Yahoo Finance (익일 종가 반영)</p>"
    else:
        earnings_html = "<p style='color:#ef4444;'>해당 종목의 실적 데이터를 불러올 수 없습니다.</p>"
        
    return market_cap, earnings_html

def fetch_financial_data(ticker_symbol):
    """IP 차단 에러를 근본적으로 막은 무결점 메인 로직"""
    
    # 한국 주식(.KS) 자동 변환 로직
    if ticker_symbol.isdigit():
        ticker_symbol = f"{ticker_symbol}.KS"
        
    # 한국 종목 여부 판단 및 벤치마크 스위칭
    is_korean = ticker_symbol.endswith('.KS') or ticker_symbol.endswith('.KQ')
    benchmark_ticker = "^KS11" if is_korean else "^GSPC"
    benchmark_name = "코스피(KOSPI)" if is_korean else "S&P 500"

    for attempt in range(3):
        try:
            session, crumb = get_robust_session()
            
            df_1d = get_yahoo_chart(ticker_symbol, "1y", "1d", session, crumb)
            df_1h = get_yahoo_chart(ticker_symbol, "1y", "1h", session, crumb) 
            sp500_1d = get_yahoo_chart(benchmark_ticker, "1y", "1d", session, crumb)
            
            if df_1d.empty or df_1h.empty:
                import yfinance as yf
                df_1d_raw = yf.download(ticker_symbol, period="1y", interval="1d", progress=False)
                df_1h_raw = yf.download(ticker_symbol, period="1y", interval="1h", progress=False)
                sp500_raw = yf.download(benchmark_ticker, period="1y", interval="1d", progress=False)
                
                if not df_1d_raw.empty and not df_1h_raw.empty:
                    if isinstance(df_1d_raw.columns, pd.MultiIndex):
                        df_1d = pd.DataFrame({'Close': df_1d_raw['Close'].iloc[:, 0], 'Open': df_1d_raw['Open'].iloc[:, 0]})
                        df_1h = pd.DataFrame({'Close': df_1h_raw['Close'].iloc[:, 0], 'Open': df_1h_raw['Open'].iloc[:, 0]})
                        sp500_1d = pd.DataFrame({'Close': sp500_raw['Close'].iloc[:, 0], 'Open': sp500_raw['Open'].iloc[:, 0]})
                    else:
                        df_1d = df_1d_raw[['Open', 'Close']]
                        df_1h = df_1h_raw[['Open', 'Close']]
                        sp500_1d = sp500_raw[['Open', 'Close']]
                        
                    df_1d.index = pd.to_datetime(df_1d.index, utc=True)
                    df_1h.index = pd.to_datetime(df_1h.index, utc=True)
                    sp500_1d.index = pd.to_datetime(sp500_1d.index, utc=True)
                else:
                    return {"error": "차트 데이터를 가져올 수 없습니다. 종목명을 확인해주세요."}
            
            current_price = df_1d['Close'].iloc[-1]
            
            df_1d['Pct_Change'] = df_1d['Close'].pct_change() * 100
            valid_pct = df_1d['Pct_Change'].dropna()
            if not valid_pct.empty:
                max_surge_idx = valid_pct.idxmax()
                max_drop_idx = valid_pct.idxmin()
                max_surge_date = max_surge_idx.strftime('%Y-%m-%d')
                max_surge_val = valid_pct.max()
                max_drop_date = max_drop_idx.strftime('%Y-%m-%d')
                max_drop_val = valid_pct.min()
                extreme_events_str = f"🚀 최대 급등일: {max_surge_date} (+{max_surge_val:.1f}%) | 🩸 최대 급락일: {max_drop_date} ({max_drop_val:.1f}%)"
            else:
                extreme_events_str = "변동성 데이터 부족"
            
            # 실적 함수 호출
            market_cap, earnings_html = get_market_cap_and_earnings(ticker_symbol, session, crumb, df_1d, sp500_1d, is_korean, benchmark_name)

            df_1d_ma = pd.DataFrame({'Close': df_1d['Close']})
            df_1d_ma['EMA200_1D'] = df_1d_ma['Close'].ewm(span=200, adjust=False).mean()
            df_1h_ma = pd.DataFrame({'Close': df_1h['Close']})
            df_4h_ma = df_1h_ma.resample('4h').agg({'Close': 'last'}).dropna()
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
                    price_str = f"₩{row['Close']:,.0f}" if is_korean else f"${row['Close']:.2f}"
                    ma_rows.append(f"<tr><td><span style='color:{color}; font-weight:bold;'>{row['Type']}</span></td><td>{date_str}</td><td>{price_str}</td></tr>")
                    
                ma_html = "<table class='ma-table'><tr><th>상태 (최근 3회)</th><th>발생일</th><th>당시 주가</th></tr>"
                ma_html += "".join(ma_rows) + "</table>"

            def get_ret(series, days):
                if len(series) > days: return ((series.iloc[-1] - series.iloc[-(days+1)]) / series.iloc[-(days+1)]) * 100
                return 0.0

            mom_rows = []
            periods = {"1일": 1, "1개월": 21, "3개월": 63, "6개월": 126, "1년": 252}
            for p_name, p_days in periods.items():
                s_ret = get_ret(df_1d['Close'], p_days)
                n_ret = get_ret(sp500_1d['Close'], p_days)
                s_col = "#22c55e" if s_ret > 0 else "#ef4444"
                n_col = "#22c55e" if n_ret > 0 else "#ef4444"
                mom_rows.append(f"<tr><td><b>{p_name} 변동</b></td><td><span style='color:{s_col}; font-weight:bold;'>{s_ret:+.2f}%</span></td><td><span style='color:{n_col}; font-weight:bold;'>{n_ret:+.2f}%</span></td></tr>")
                
            curr_str = f"₩{current_price:,.0f}" if is_korean else f"${current_price:.2f}"
            momentum_html = f"<table class='ma-table'><tr><th>기간</th><th>{ticker_symbol} 현재가: {curr_str}</th><th>{benchmark_name} 비교</th></tr>"
            momentum_html += "".join(mom_rows) + "</table>"
            
            raw_news = fetch_investing_news(ticker_symbol)

            return {
                "market_cap": market_cap,
                "last_cross_type": last_cross_type,
                "last_cross_date": last_cross_date,
                "ma_html": ma_html,
                "momentum_html": momentum_html,
                "earnings_html": earnings_html,
                "raw_news": raw_news,
                "extreme_events": extreme_events_str
            }
        except Exception as e:
            time.sleep(2)
            if attempt == 2:
                return {"error": f"데이터를 불러오는 데 실패했습니다. 다시 시도해주세요. 오류: {e}"}
            continue

def analyze_sector_with_ai(ticker, sector, fin_data, user_issue, news_content):
    from api_utils import ask_gemini_dynamic
    today = datetime.now().strftime('%Y-%m-%d')
    extreme_info = fin_data.get('extreme_events', '')
    
    prompt = f"""
    당신은 월스트리트 수석 애널리스트입니다. 아래 데이터를 바탕으로 완벽한 투자 분석 보고서를 마크다운으로 작성하세요.
    
    [분석 대상]
    - 종목: {ticker} (섹터: {sector}) | 기준일: {today}
    - 최근 1년 핵심 급변동 기록: {extreme_info}
    - 수집된 최근 구글 뉴스: {fin_data.get('raw_news', '')}
    - 나의 핵심 관점: {user_issue}
    
    [🚨 핵심 지시사항: 과거 팩트체크 초강제]
    1. 방금 제공된 뉴스는 최근 치에 불과합니다. 따라서 위 [핵심 급변동 기록]에 명시된 날짜의 급등/급락 원인은 **당신의 사전 지식을 100% 동원하여 정확히 찾아내야** 합니다!
    2. 절대 "알 수 없다"고 쓰지 마세요. 무조건 구체적인 촉매제를 표에 채워 넣으세요.
    3. 종합 의견 작성 시, 무조건 긍정적으로 포장하지 마세요. 리스크 요인을 반드시 비판적으로 서술하세요.
    
    [보고서 필수 목차 및 양식]
    ## 🏢 {ticker} 심층 분석 보고서 ({today} 기준)
    ### 1. 📊 시장 위치 및 핵심 밸류체인 요약
    ### 2. 🚨 최근 1년 10% 이상 급변동 사유 팩트체크
    | 발생 시점 | 변동 방향 | 구체적 촉매제 (당신의 지식 총동원) | 펀더멘털 파급력 |
    |---|---|---|---|
    | (예: {extreme_info.split('|')[0] if extreme_info else ''}) | 상승/하락 | (예: 실적 서프라이즈) | ... |
    ### 3. 💰 실적 및 모멘텀 종합 의견 (비판적 시각 필수 포함)
    ### 4. 💡 기관 트레이딩 결론 (Actionable Insight)
    - **현재 포지션:** (롱/숏/관망 택 1)
    - **핵심 리스크:**
    - **최종 Action:** """
    
    return ask_gemini_dynamic(prompt, [])
