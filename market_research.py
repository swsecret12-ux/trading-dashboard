import pandas as pd
import requests
from datetime import datetime, timezone
import urllib.parse
import xml.etree.ElementTree as ET
import time
import random
import yfinance as yf
import numpy as np
import json

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

def get_earnings_alternative(ticker):
    """
    💡 [탈(脫) 야후 무적 패치] 
    1. 에러를 뿜는 야후 파이낸스를 완전히 버리고 나스닥(NASDAQ) 공식 API를 1차로 뚫고 들어갑니다.
    2. 나스닥도 막히면, AllOrigins 글로벌 프록시 네트워크를 통해 다른 나라 IP로 우회하여 강제 추출합니다.
    """
    clean_ticker = ticker.replace('.KS', '').replace('.KQ', '')
    records = []
    
    # [1단계] 나스닥(NASDAQ) 공식 API 다이렉트 호출
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/"
    }
    
    try:
        # 1-1. 과거 실적 및 서프라이즈
        url_history = f"https://api.nasdaq.com/api/company/{clean_ticker}/earnings-surprise"
        res = requests.get(url_history, headers=headers, timeout=5)
        if res.status_code == 200:
            rows = res.json().get('data', {}).get('earningsSurpriseTable', {}).get('rows', [])
            for r in rows:
                date_str = r.get('dateReported')
                if not date_str: continue
                try:
                    dt = pd.to_datetime(date_str).tz_localize('UTC')
                    eps_est = float(r.get('consensusForecast')) if r.get('consensusForecast') else pd.NA
                    eps_act = float(r.get('eps')) if r.get('eps') else pd.NA
                    surp = float(r.get('percentageSurprise')) / 100.0 if r.get('percentageSurprise') else pd.NA
                    records.append({
                        'Date': dt, 'EPS Estimate': eps_est, 'Reported EPS': eps_act, 'Surprise(%)': surp
                    })
                except: continue
                
        # 1-2. 다가오는 미래 실적 발표일
        url_next = f"https://api.nasdaq.com/api/analyst/{clean_ticker}/earnings-date"
        res_next = requests.get(url_next, headers=headers, timeout=5)
        if res_next.status_code == 200:
            announcement = res_next.json().get('data', {}).get('announcement', '')
            if announcement:
                dt_next = pd.to_datetime(announcement).tz_localize('UTC')
                exists = any(r['Date'].strftime('%Y-%m-%d') == dt_next.strftime('%Y-%m-%d') for r in records)
                if not exists:
                    records.append({
                        'Date': dt_next, 'EPS Estimate': pd.NA, 'Reported EPS': pd.NA, 'Surprise(%)': pd.NA
                    })
    except: pass

    # [2단계] 나스닥 API도 서버를 튕겨낸다면? -> AllOrigins (글로벌 프록시 우회) API 호출!
    # 스트림릿 서버 IP가 아닌, 프록시 서버의 IP를 통해 야후 데이터를 몰래 빼옵니다.
    if not records:
        try:
            target_url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=earningsHistory,calendarEvents"
            proxy_url = f"https://api.allorigins.win/get?url={urllib.parse.quote(target_url)}"
            
            res_proxy = requests.get(proxy_url, timeout=10)
            if res_proxy.status_code == 200:
                proxy_contents = res_proxy.json().get('contents', '{}')
                proxy_data = json.loads(proxy_contents)
                result = proxy_data.get('quoteSummary', {}).get('result', [])
                
                if result:
                    hist = result[0].get("earningsHistory", {}).get("history", [])
                    for h in hist:
                        dt_fmt = h.get("quarter", {}).get("fmt")
                        if not dt_fmt: continue
                        records.append({
                            "Date": pd.to_datetime(dt_fmt).tz_localize('UTC'),
                            "EPS Estimate": h.get("epsEstimate", {}).get("raw", pd.NA),
                            "Reported EPS": h.get("epsActual", {}).get("raw", pd.NA),
                            "Surprise(%)": h.get("surprisePercent", {}).get("raw", pd.NA)
                        })
                    
                    cal = result[0].get("calendarEvents", {}).get("earnings", {})
                    for nd in cal.get("earningsDate", []):
                        ts = nd.get("raw")
                        if ts:
                            records.append({
                                "Date": pd.to_datetime(ts, unit="s").tz_localize('UTC'),
                                "EPS Estimate": cal.get("earningsAverage", {}).get("raw", pd.NA),
                                "Reported EPS": pd.NA,
                                "Surprise(%)": pd.NA
                            })
        except: pass

    if not records:
        return pd.DataFrame()
    
    df = pd.DataFrame(records)
    df = df.sort_values('Date', ascending=False).drop_duplicates(subset=['Date'])
    return df.set_index('Date')

def get_market_cap_and_earnings(ticker, hist_df):
    """무적 API로 긁어온 데이터를 영우님의 천재적인 D-1, D, D+1 로직과 결합합니다!"""
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

    # 💡 야후 모듈을 버리고, 나스닥 & 프록시 우회 크롤러를 호출합니다!
    earn_df = get_earnings_alternative(ticker)

    if not earn_df.empty:
        now_tz = pd.Timestamp.now(tz='UTC')

        for idx_date, row in earn_df.iterrows():
            date_str = idx_date.strftime('%Y-%m-%d')
            eps_est = row.get('EPS Estimate', pd.NA)
            eps_act = row.get('Reported EPS', pd.NA)
            surp = row.get('Surprise(%)', pd.NA)

            # 다가오는 미래 날짜는 가장 윗줄에 노란색으로 고정!
            if idx_date > now_tz and pd.isna(eps_act):
                if not upcoming_row:
                    est_str = f"{eps_est:.2f}" if pd.notna(eps_est) else "-"
                    upcoming_row = f"<tr style='background-color:#fffbea;'><td style='color:#64748b;'>⏳ {date_str} (예정)</td><td style='color:#64748b;'>{est_str}</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>"
                continue

            if pd.isna(eps_act) and pd.isna(eps_est): continue 

            est_str = f"{eps_est:.2f}" if pd.notna(eps_est) else "-"
            act_str = f"{eps_act:.2f}" if pd.notna(eps_act) else "-"

            surp_html = "-"
            if pd.notna(surp):
                surp_val = surp * 100
                color = "#22c55e" if surp_val > 0 else "#ef4444"
                surp_html = f"<span style='color:{color}; font-weight:bold;'>{surp_val:+.1f}%</span>"

            # 핵심 로직: D-1, D, D+1 주가 변동률 추적
            t_minus_1, t_0, t_plus_1 = "-", "-", "-"
            
            # 오늘 기준 비교
            now_date_str = now_tz.strftime('%Y-%m-%d')
            if date_str > now_date_str:
                t_minus_1, t_0, t_plus_1 = "대기중", "대기중", "대기중"
            else:
                # 해당 발표일 혹은 가장 가까운 다음 거래일 찾기
                future_or_exact = [d for d in hist_dates if d >= date_str]
                if future_or_exact:
                    idx_pos = hist_dates.index(future_or_exact[0])
                    
                    def get_pct(pos):
                        if pos < 1 or pos >= len(hist_df): return "-"
                        pct = hist_df['Pct_Change'].iloc[pos]
                        c = "#22c55e" if pct > 0 else "#ef4444"
                        return f"<span style='color:{c}; font-weight:bold;'>{pct:+.2f}%</span>"
                    
                    t_minus_1 = get_pct(idx_pos - 1)
                    t_0 = get_pct(idx_pos)
                    
                    if idx_pos + 1 < len(hist_df):
                        t_plus_1 = get_pct(idx_pos + 1)
                    else:
                        t_plus_1 = "아직 안나옴"
                else:
                    t_minus_1, t_0, t_plus_1 = "-", "-", "-"

            rows.append(f"<tr><td>{date_str}</td><td>{est_str}</td><td>{act_str}</td><td>{surp_html}</td><td>{t_minus_1}</td><td>{t_0}</td><td>{t_plus_1}</td></tr>")

    final_rows = []
    if upcoming_row: final_rows.append(upcoming_row)
    final_rows.extend(rows)

    if final_rows:
        earnings_html = f"<table class='ma-table'><tr><th>발표일(분기)</th><th>예상 EPS</th><th>실측 EPS</th><th>서프라이즈</th><th>발표 전일(D-1)</th><th>당일(D)</th><th>익일(D+1)</th></tr>"
        earnings_html += "".join(final_rows) + "</table>"
        earnings_html += "<p style='font-size: 0.85rem; color: #666; margin-top: 5px;'>* D-1, D, D+1은 해당 일자의 <strong>전일 종가 대비 변동률(%)</strong>입니다.</p>"
    else:
        earnings_html = "<p style='color:#ef4444;'>해당 종목의 실적 데이터를 불러올 수 없거나 제공되지 않습니다.</p>"
        
    return market_cap, earnings_html

def get_valuation_html(ticker_symbol, is_korean):
    """EPS와 PER을 기반으로 기업의 가치와 적정 주가를 산출하는 함수"""
    try:
        tkr = yf.Ticker(ticker_symbol)
        info = tkr.info
        
        curr_price = info.get('currentPrice', info.get('previousClose', 0))
        trailing_pe = info.get('trailingPE', 0)
        trailing_eps = info.get('trailingEps', 0)
        forward_eps = info.get('forwardEps', 0)
        target_price = info.get('targetMeanPrice', 0)
        
        if not trailing_pe or not trailing_eps:
            return "<p style='color:#64748b;'>PER/EPS 밸류에이션 데이터가 제공되지 않는 종목입니다.</p>"
            
        # 기대 적정주가 계산 (내년 예상 EPS * 현재 프리미엄 PER)
        calc_forward_price = trailing_pe * forward_eps if isinstance(trailing_pe, (int, float)) and isinstance(forward_eps, (int, float)) else 0
        
        sym = "₩" if is_korean else "$"
        fmt = ",.0f" if is_korean else ".2f"
        
        html = "<table class='ma-table'>"
        html += "<tr><th>현재 주가</th><th>현재 PER</th><th>현재 EPS (TTM)</th><th>내년 예상 EPS</th><th>기대 적정주가</th><th>월가 목표가</th></tr>"
        html += "<tr>"
        html += f"<td>{sym}{curr_price:{fmt}}</td>" if isinstance(curr_price, (int, float)) else "<td>-</td>"
        html += f"<td>{trailing_pe:.2f}배</td>" if isinstance(trailing_pe, (int, float)) else "<td>-</td>"
        html += f"<td>{sym}{trailing_eps:{fmt}}</td>" if isinstance(trailing_eps, (int, float)) else "<td>-</td>"
        html += f"<td>{sym}{forward_eps:{fmt}}</td>" if isinstance(forward_eps, (int, float)) else "<td>-</td>"
        
        if calc_forward_price:
            color = "#22c55e" if calc_forward_price > curr_price else "#ef4444"
            html += f"<td><span style='color:{color}; font-weight:bold;'>{sym}{calc_forward_price:{fmt}}</span></td>"
        else:
            html += "<td>-</td>"
            
        html += f"<td>{sym}{target_price:{fmt}}</td>" if isinstance(target_price, (int, float)) else "<td>-</td>"
        html += "</tr>"
        html += "</table>"
        html += "<p style='font-size: 0.85rem; color: #666; margin-top: 5px;'>* <strong>기대 적정주가</strong> = 내년 예상 EPS × 현재 PER<br>*(현재 시장이 부여하는 기대치(PER)가 내년에도 동일하게 유지된다고 가정했을 때의 산술적 목표가입니다.)</p>"
        
        return html
    except Exception as e:
        return f"<p style='color:#ef4444;'>가치 평가 데이터를 불러올 수 없습니다. ({str(e)})</p>"

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
            
            # 실적 함수 호출 (D-1, D, D+1 로직 적용)
            market_cap, earnings_html = get_market_cap_and_earnings(ticker_symbol, df_1d)
            
            # EPS/PER 기반 밸류에이션(가치 평가) 로직 호출
            valuation_html = get_valuation_html(ticker_symbol, is_korean)

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
                "valuation_html": valuation_html,
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
    import time
    
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
    
    # 💡 [핵심 패치] 무료 API 한도 초과(429) 시 자동으로 25초 대기 후 끈질기게 재시도하는 로직 추가!
    for attempt in range(3):
        result = ask_gemini_dynamic(prompt, [])
        if "429" in result or "quota" in result.lower() or "소진" in result:
            if attempt < 2:
                time.sleep(25)  # 25초 푹 쉬고 다시 구글 문을 두드립니다.
                continue
        return result
        
    return "API 호출 한도 초과로 분석을 완료하지 못했습니다. 잠시 후 다시 시도해주세요."
