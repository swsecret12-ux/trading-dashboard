import pandas as pd
import requests
from bs4 import BeautifulSoup
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
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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

def get_korean_stock_info(ticker):
    """야후 접속 차단을 막기 위해 네이버 금융을 크롤링하여 한국 주식의 종목명, 시총, PER, EPS 등을 완벽하게 가져옵니다."""
    clean_ticker = ticker.replace('.KS', '').replace('.KQ', '')
    company_name = clean_ticker
    market_cap_usd = 0.0
    valuation_html = "<p style='color:#64748b;'>가치 평가 데이터가 제공되지 않습니다.</p>"
    
    try:
        # 네이버 금융 웹페이지 직접 크롤링 (Too Many Requests 방어)
        url_web = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
        res_web = requests.get(url_web, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res_web.text, 'html.parser')
        
        # 1. 회사 이름 추출
        name_tag = soup.select_one('.wrap_company h2 a')
        if name_tag: company_name = name_tag.text.strip()
        
        # 2. 시가총액 추출 (억원)
        mcap_tag = soup.select_one('#_market_sum')
        if mcap_tag:
            mcap_str = mcap_tag.text.replace(',', '').replace('\t', '').replace('\n', '')
            if mcap_str.isdigit():
                mcap_100m = float(mcap_str)
                # 억원 -> 원 -> 달러 변환 (미국 주식과 단위 통일을 위해 임시 변환)
                market_cap_usd = (mcap_100m * 100000000) / 1380 
        
        # 3. 현재가, PER, EPS 추출
        curr_price_str = soup.select_one('.no_today .blind').text.replace(',', '') if soup.select_one('.no_today .blind') else "0"
        curr_price = float(curr_price_str) if curr_price_str.isdigit() else 0
        
        per_str = soup.select_one('#_per').text.replace(',', '') if soup.select_one('#_per') else "0"
        eps_str = soup.select_one('#_eps').text.replace(',', '') if soup.select_one('#_eps') else "0"
        
        per = float(per_str) if per_str.replace('.','',1).isdigit() else 0
        eps = float(eps_str) if eps_str.replace('.','',1).isdigit() else 0
        
        # html 표 제작
        html = "<table class='ma-table'>"
        html += "<tr><th>현재 주가</th><th>현재 PER</th><th>현재 EPS</th><th>산출 기준</th></tr>"
        html += "<tr>"
        html += f"<td>₩{curr_price:,.0f}</td>" if curr_price else "<td>-</td>"
        html += f"<td>{per:.2f}배</td>" if per else "<td>-</td>"
        html += f"<td>₩{eps:,.0f}</td>" if eps else "<td>-</td>"
        html += "<td>네이버 금융 제공</td>"
        html += "</tr></table>"
        valuation_html = html
            
    except Exception as e:
        valuation_html = f"<p style='color:#ef4444;'>한국 종목 가치 평가 데이터를 불러올 수 없습니다. ({str(e)})</p>"
        
    return company_name, market_cap_usd, valuation_html

def fetch_investing_news(ticker, company_name=""):
    """회사 이름(Name)을 우선적으로 사용하여 구글 뉴스를 정밀 타격 검색합니다."""
    try:
        search_term = company_name if company_name else ticker
        query = urllib.parse.quote(f"{search_term} (주식 OR 실적 OR 전망 OR 호재)")
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
        return "\n".join(news_items) if news_items else f"[{search_term}]에 대한 최근 구글 뉴스가 없습니다."
    except: return "뉴스 수집 실패 (Google RSS 우회 실패)"

def get_earnings_alternative(ticker):
    """나스닥 공식 API & AllOrigins 우회 병합 실적 크롤러 (미국 전용)"""
    clean_ticker = ticker.replace('.KS', '').replace('.KQ', '')
    records = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/"
    }
    
    try:
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
                    records.append({'Date': dt, 'EPS Estimate': eps_est, 'Reported EPS': eps_act, 'Surprise(%)': surp})
                except: continue
    except: pass

    if not records:
        try:
            target_url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=earningsHistory,calendarEvents"
            proxy_url = f"https://api.allorigins.win/get?url={urllib.parse.quote(target_url)}"
            
            res_proxy = requests.get(proxy_url, timeout=10)
            if res_proxy.status_code == 200:
                proxy_data = json.loads(res_proxy.json().get('contents', '{}'))
                result = proxy_data.get('quoteSummary', {}).get('result', [])
                
                if result:
                    for h in result[0].get("earningsHistory", {}).get("history", []):
                        dt_fmt = h.get("quarter", {}).get("fmt")
                        if not dt_fmt: continue
                        records.append({
                            "Date": pd.to_datetime(dt_fmt).tz_localize('UTC'),
                            "EPS Estimate": h.get("epsEstimate", {}).get("raw", pd.NA),
                            "Reported EPS": h.get("epsActual", {}).get("raw", pd.NA),
                            "Surprise(%)": h.get("surprisePercent", {}).get("raw", pd.NA)
                        })
        except: pass

    if not records: return pd.DataFrame()
    df = pd.DataFrame(records).sort_values('Date', ascending=False).drop_duplicates(subset=['Date'])
    return df.set_index('Date')

def get_valuation_html(ticker_symbol):
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
            
        calc_forward_price = trailing_pe * forward_eps if isinstance(trailing_pe, (int, float)) and isinstance(forward_eps, (int, float)) else 0
        
        html = "<table class='ma-table'>"
        html += "<tr><th>현재 주가</th><th>현재 PER</th><th>현재 EPS(TTM)</th><th>내년 예상 EPS</th><th>기대 적정주가</th><th>월가 목표가</th></tr>"
        html += "<tr>"
        html += f"<td>${curr_price:.2f}</td>" if isinstance(curr_price, (int, float)) else "<td>-</td>"
        html += f"<td>{trailing_pe:.2f}배</td>" if isinstance(trailing_pe, (int, float)) else "<td>-</td>"
        html += f"<td>${trailing_eps:.2f}</td>" if isinstance(trailing_eps, (int, float)) else "<td>-</td>"
        html += f"<td>${forward_eps:.2f}</td>" if isinstance(forward_eps, (int, float)) else "<td>-</td>"
        
        if calc_forward_price:
            color = "#22c55e" if calc_forward_price > curr_price else "#ef4444"
            html += f"<td><span style='color:{color}; font-weight:bold;'>${calc_forward_price:.2f}</span></td>"
        else: html += "<td>-</td>"
            
        html += f"<td>${target_price:.2f}</td>" if isinstance(target_price, (int, float)) else "<td>-</td>"
        html += "</tr></table>"
        html += "<p style='font-size: 0.85rem; color: #666; margin-top: 5px;'>* <strong>기대 적정주가</strong> = 내년 예상 EPS × 현재 PER</p>"
        return html
    except Exception as e:
        if "429" in str(e) or "Too Many Requests" in str(e):
            return "<p style='color:#ef4444;'>가치 평가 데이터를 불러올 수 없습니다. (야후 파이낸스 접속량 제한 방어됨. 잠시 후 시도하세요)</p>"
        return f"<p style='color:#ef4444;'>가치 평가 데이터를 불러올 수 없습니다. ({str(e)})</p>"

def get_market_cap_and_earnings(ticker, is_korean):
    if is_korean:
        # 💡 핵심 픽스: 한국 주식은 나스닥 API나 야후 실적을 찌르지 않고 안내 멘트만 출력 (429 차단 원천 봉쇄)
        return "<p style='color:#64748b;'>한국 종목의 상세 분기별 어닝 서프라이즈 데이터는 지원되지 않습니다. 상단의 네이버 금융 기준 <b>기업 가치(PER/EPS)</b>를 참고해 주세요.</p>"
        
    earnings_html = ""
    rows = []
    
    earn_df = get_earnings_alternative(ticker)
    if not earn_df.empty:
        for idx_date, row in earn_df.iterrows():
            date_str = idx_date.strftime('%Y-%m-%d')
            eps_est = row.get('EPS Estimate', pd.NA)
            eps_act = row.get('Reported EPS', pd.NA)
            surp = row.get('Surprise(%)', pd.NA)

            if pd.isna(eps_act) and pd.isna(eps_est): continue 

            est_str = f"{eps_est:.2f}" if pd.notna(eps_est) else "-"
            act_str = f"{eps_act:.2f}" if pd.notna(eps_act) else "-"

            surp_html = "-"
            if pd.notna(surp):
                surp_val = surp * 100
                color = "#22c55e" if surp_val > 0 else "#ef4444"
                surp_html = f"<span style='color:{color}; font-weight:bold;'>{surp_val:+.1f}%</span>"

            rows.append(f"<tr><td>{date_str}</td><td>{est_str}</td><td>{act_str}</td><td>{surp_html}</td></tr>")

    if rows:
        earnings_html = f"<table class='ma-table'><tr><th>발표일(분기)</th><th>예상 EPS</th><th>실측 EPS</th><th>서프라이즈</th></tr>"
        earnings_html += "".join(rows) + "</table>"
    else:
        earnings_html = "<p style='color:#ef4444;'>해당 종목의 분기 실적 데이터를 불러올 수 없거나 제공되지 않습니다.</p>"
        
    return earnings_html

def parse_yf_df(raw_df):
    """yfinance 최신 버전의 MultiIndex 반환 꼬임을 방지하는 안전 파서"""
    if raw_df.empty: return pd.DataFrame(columns=['Open', 'Close'])
    if isinstance(raw_df.columns, pd.MultiIndex):
        try:
            return pd.DataFrame({'Open': raw_df['Open'].iloc[:, 0], 'Close': raw_df['Close'].iloc[:, 0]})
        except:
            pass
    return raw_df[['Open', 'Close']]

def fetch_financial_data(ticker_symbol):
    # 한국 주식 판단 로직
    if ticker_symbol.isdigit(): ticker_symbol = f"{ticker_symbol}.KS"
    is_korean = ticker_symbol.endswith('.KS') or ticker_symbol.endswith('.KQ')
    benchmark_ticker = "^KS11" if is_korean else "^IXIC" 
    benchmark_name = "코스피(KOSPI)" if is_korean else "나스닥(NASDAQ)"

    # 회사 이름 및 시가총액/가치평가 초기화
    company_name = ""
    market_cap = 0.0
    valuation_html = ""
    
    if is_korean:
        # 💡 한국 종목은 네이버에서 직접 크롤링하여 에러 0% 보장
        company_name, market_cap, valuation_html = get_korean_stock_info(ticker_symbol)
    else:
        try:
            tkr = yf.Ticker(ticker_symbol)
            company_name = tkr.info.get('longName', tkr.info.get('shortName', ''))
            market_cap = tkr.info.get('marketCap', 0.0)
            valuation_html = get_valuation_html(ticker_symbol)
        except: pass

    for attempt in range(3):
        try:
            # 💡 핵심 픽스 1: 1시간봉(1h) 요청 기간을 야후 제한(730일)에 걸리지 않도록 1y(1년)로 단축!
            # 💡 핵심 픽스 2: 최신 yfinance 충돌을 막기 위해 session 강제 주입 제거
            df_1d_raw = yf.download(ticker_symbol, period="2y", interval="1d", progress=False)
            df_1h_raw = yf.download(ticker_symbol, period="1y", interval="1h", progress=False)
            bm_raw = yf.download(benchmark_ticker, period="2y", interval="1d", progress=False)
            
            # 💡 핵심 픽스 3: 1시간봉이 없다고 전체 분석을 죽이지 않고, 일봉(1d)만이라도 살아있으면 무조건 통과!
            if df_1d_raw.empty:
                return {"error": f"일봉 차트 데이터를 가져올 수 없습니다. 야후 파이낸스에 '{ticker_symbol}' 종목이 존재하는지 확인해주세요."}
                
            df_1d = parse_yf_df(df_1d_raw)
            df_1h = parse_yf_df(df_1h_raw)
            bm_1d = parse_yf_df(bm_raw)
                
            df_1d.index = pd.to_datetime(df_1d.index, utc=True)
            bm_1d.index = pd.to_datetime(bm_1d.index, utc=True)
            df_1d = df_1d.dropna(subset=['Close'])
            bm_1d = bm_1d.dropna(subset=['Close'])

            current_price = df_1d['Close'].iloc[-1]
            df_1d['Prev_Close'] = df_1d['Close'].shift(1)
            bm_1d['Prev_Close'] = bm_1d['Close'].shift(1)
            
            df_1d['Pct_Change'] = df_1d['Close'].pct_change() * 100
            bm_1d['Pct_Change'] = bm_1d['Close'].pct_change() * 100
            
            extreme_df = df_1d[df_1d['Pct_Change'].abs() >= 8.0].copy()
            if not extreme_df.empty:
                extreme_df['abs_change'] = extreme_df['Pct_Change'].abs()
                extreme_df = extreme_df.sort_values('abs_change', ascending=False).head(10).sort_index()
                events = []
                for date_idx, row in extreme_df.iterrows():
                    date_str = date_idx.strftime('%Y-%m-%d')
                    pct = row['Pct_Change']
                    curr_p = row['Close']
                    prev_p = row['Prev_Close']
                    
                    try: 
                        bm_pct = bm_1d.loc[date_idx, 'Pct_Change']
                        bm_curr = bm_1d.loc[date_idx, 'Close']
                        bm_prev = bm_1d.loc[date_idx, 'Prev_Close']
                    except: 
                        bm_pct, bm_curr, bm_prev = 0.0, 0.0, 0.0
                    
                    icon = "🚀 급등" if pct > 0 else "🩸 급락"
                    events.append(f"- {date_str} ({icon}): 종목 {pct:+.1f}% ({prev_p:.2f} ➡️ {curr_p:.2f}), 벤치마크 {bm_pct:+.1f}% ({bm_prev:.2f} ➡️ {bm_curr:.2f})")
                extreme_events_str = "\n".join(events)
            else:
                extreme_events_str = "8% 이상 급변동일 없음"
            
            # 실적 가져오기
            earnings_html = get_market_cap_and_earnings(ticker_symbol, is_korean)

            # 4H/1D 크로스 계산 (1시간봉 데이터가 정상적으로 있을 때만 계산)
            if df_1h.empty:
                ma_html = "<p style='color:#ef4444;'>해당 종목은 1시간봉 차트 데이터가 제공되지 않아 크로스 분석이 불가능합니다.</p>"
                last_cross_type, last_cross_date = "데이터 없음", "-"
            else:
                df_1h.index = pd.to_datetime(df_1h.index, utc=True)
                df_1h = df_1h.dropna(subset=['Close'])
                
                df_1d_ma = pd.DataFrame({'Close': df_1d['Close']})
                df_1d_ma['EMA200_1D'] = df_1d_ma['Close'].ewm(span=200, adjust=False).mean()
                
                df_1h_ma = pd.DataFrame({'Close': df_1h['Close']})
                df_4h_ma = df_1h_ma.resample('4h').agg({'Close': 'last'}).dropna()
                df_4h_ma['EMA200_4H'] = df_4h_ma['Close'].ewm(span=200, adjust=False).mean()
                
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
                    last_cross_type, last_cross_date = "크로스 없음", "-"
                else:
                    last_cross_type = crosses.iloc[-1]['Type']
                    last_cross_date = crosses.index[-1].strftime('%Y-%m-%d %H:%M')
                    ma_rows = []
                    for idx, row in crosses.tail(3)[::-1].iterrows():
                        color = "#22c55e" if "골든" in row['Type'] else "#ef4444"
                        date_str = idx.strftime('%Y-%m-%d %H:%M')
                        price_str = f"₩{row['Close']:,.0f}" if is_korean else f"${row['Close']:.2f}"
                        ma_rows.append(f"<tr><td><span style='color:{color}; font-weight:bold;'>{row['Type']}</span></td><td>{date_str}</td><td>{price_str}</td></tr>")
                    ma_html = "<table class='ma-table'><tr><th>상태 (최근 3회)</th><th>발생일</th><th>당시 주가</th></tr>" + "".join(ma_rows) + "</table>"

            def get_ret(series, days):
                if len(series) > days: return ((series.iloc[-1] - series.iloc[-(days+1)]) / series.iloc[-(days+1)]) * 100
                return 0.0

            mom_rows = []
            periods = {"1일": 1, "1개월": 21, "3개월": 63, "6개월": 126, "1년": 252}
            for p_name, p_days in periods.items():
                s_ret = get_ret(df_1d['Close'], p_days)
                n_ret = get_ret(bm_1d['Close'], p_days)
                s_col = "#22c55e" if s_ret > 0 else "#ef4444"
                n_col = "#22c55e" if n_ret > 0 else "#ef4444"
                mom_rows.append(f"<tr><td><b>{p_name} 변동</b></td><td><span style='color:{s_col}; font-weight:bold;'>{s_ret:+.2f}%</span></td><td><span style='color:{n_col}; font-weight:bold;'>{n_ret:+.2f}%</span></td></tr>")
                
            curr_str = f"₩{current_price:,.0f}" if is_korean else f"${current_price:.2f}"
            momentum_html = f"<table class='ma-table'><tr><th>기간</th><th>현재가: {curr_str}</th><th>{benchmark_name} 비교</th></tr>" + "".join(mom_rows) + "</table>"
            
            # 💡 핵심 픽스: 추출해온 회사 이름(company_name)을 뉴스 검색기에 전달!
            raw_news = fetch_investing_news(ticker_symbol, company_name)

            return {
                "company_name": company_name, 
                "market_cap": market_cap, "last_cross_type": last_cross_type, "last_cross_date": last_cross_date,
                "ma_html": ma_html, "momentum_html": momentum_html, "earnings_html": earnings_html,
                "valuation_html": valuation_html, "raw_news": raw_news, "extreme_events": extreme_events_str
            }
        except Exception as e:
            time.sleep(2)
            if attempt == 2: return {"error": f"데이터를 불러오는 데 실패했습니다. 다시 시도해주세요. 오류: {e}"}
            continue

def analyze_sector_with_ai(ticker, company_name, sector, fin_data, user_issue, news_content):
    from api_utils import ask_gemini_dynamic
    import time
    
    today = datetime.now().strftime('%Y-%m-%d')
    extreme_info = fin_data.get('extreme_events', '')
    
    # 💡 핵심 픽스: AI 프롬프트에 '회사 이름(company_name)'을 명확하게 심어주어 분석 수준을 높임
    display_name = f"{company_name} ({ticker})" if company_name else ticker
    
    prompt = f"""
    당신은 월스트리트 수석 애널리스트입니다. 아래 데이터를 바탕으로 완벽하고 '깊이 있는' 투자 분석 보고서를 마크다운으로 작성하세요.
    
    [분석 대상]
    - 종목: {display_name} (섹터: {sector}) | 기준일: {today}
    - 최근 1년 8% 이상 핵심 급변동 기록 (최대 10개, 가격 변화 포함):
    {extreme_info}
    - 수집된 최근 구글 뉴스: {fin_data.get('raw_news', '')}
    - 나의 핵심 관점: {user_issue}
    
    [🚨 핵심 지시사항]
    1. 방금 제공된 뉴스는 최근 치에 불과합니다. 따라서 위 [핵심 급변동 기록]에 명시된 날짜별 원인은 당신의 방대한 사전 지식을 동원하여 정확히 찾아내세요.
    2. 1번, 3번, 4번 목차는 월스트리트 전문 보고서처럼 **풍부하고 깊이 있는 인사이트와 상세한 분석**을 제공하세요. (절대 내용을 너무 짧게 줄이지 마세요!)
    3. 종합 의견 작성 시, 리스크 요인을 반드시 포함하고 다각도로 분석하세요.
    
    [보고서 필수 목차 및 양식]
    ## 🏢 {display_name} 심층 분석 보고서 ({today} 기준)
    ### 1. 📊 시장 위치 및 핵심 밸류체인 상세 요약 (깊이 있게 작성)
    ### 2. 🚨 최근 1년 8% 이상 급변동 사유 팩트체크 (최대 10개)
    | 발생 날짜<br>(구분) | 종목 등락률<br>(가격 변화) | 벤치마크 등락률<br>(지수 변화) | 구체적 촉매제 (당신의 지식 총동원, 핵심 요약) | 펀더멘털 파급력 |
    |---|---|---|---|---|
    (⚠️표 작성 주의사항: 
    1. 위 [핵심 급변동 기록]의 날짜를 단 하나도 빠짐없이 10개 모두 행으로 작성할 것. 
    2. 엑셀처럼 깔끔하게 보이도록, 수치 옆의 '(가격 ➡️ 가격)' 부분은 등락률 퍼센트 뒤에 HTML 태그 `<br>`를 붙여서 줄바꿈하여 기입할 것. 
    3. 발생 날짜 옆에 (🚀 급등) 또는 (🩸 급락) 표기를 반드시 포함할 것.)
    ### 3. 💰 실적 및 모멘텀 종합 의견 (상세하고 풍부하게 분석)
    ### 4. 💡 기관 트레이딩 결론
    - **현재 포지션:** (롱/숏/관망 택 1)
    - **핵심 정량적 리스크:** (상세 서술)
    - **최종 Action:** (상세 서술) """
    
    for attempt in range(3):
        result = ask_gemini_dynamic(prompt, [])
        if "429" in result or "quota" in result.lower() or "소진" in result:
            if attempt < 2:
                time.sleep(20) 
                continue
        return result
        
    return "API 호출 한도 초과로 분석을 완료하지 못했습니다. 잠시 후 다시 시도해주세요."
