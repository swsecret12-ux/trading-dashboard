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
    """한국 주식 전용: 기업 정보, 친절한 가치평가(PER/EPS 해설), 4분기 실적 표를 크롤링"""
    clean_ticker = ticker.replace('.KS', '').replace('.KQ', '')
    company_name = clean_ticker
    market_cap_usd = 0.0
    valuation_html = "<p style='color:#64748b;'>가치 평가 데이터가 제공되지 않습니다.</p>"
    earnings_html = "<p style='color:#ef4444;'>실적 데이터를 불러올 수 없거나 제공되지 않습니다.</p>"
    
    try:
        url_web = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
        res_web = requests.get(url_web, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res_web.text, 'html.parser')
        
        # 1. 회사 이름 & 시총 추출
        name_tag = soup.select_one('.wrap_company h2 a')
        if name_tag: company_name = name_tag.text.strip()
        
        mcap_tag = soup.select_one('#_market_sum')
        if mcap_tag:
            mcap_str = mcap_tag.text.replace(',', '').replace('\t', '').replace('\n', '')
            if mcap_str.isdigit():
                mcap_100m = float(mcap_str)
                market_cap_usd = (mcap_100m * 100000000) / 1380 
        
        # 2. 초보자를 위한 가치 평가 해설 (EPS, PER, 적정주가)
        curr_price_str = soup.select_one('.no_today .blind').text.replace(',', '') if soup.select_one('.no_today .blind') else "0"
        curr_price = float(curr_price_str) if curr_price_str.isdigit() else 0
        per_str = soup.select_one('#_per').text.replace(',', '') if soup.select_one('#_per') else "0"
        eps_str = soup.select_one('#_eps').text.replace(',', '') if soup.select_one('#_eps') else "0"
        per = float(per_str) if per_str.replace('.','',1).isdigit() else 0
        eps = float(eps_str) if eps_str.replace('.','',1).isdigit() else 0
        
        target_price_tag = soup.select_one('.r_cmp_inv .f_up em')
        target_price_str = target_price_tag.text.replace(',', '') if target_price_tag else "0"
        target_price = float(target_price_str) if target_price_str.isdigit() else 0
        
        fair_value = eps * 10 # 코스피 평균 수준(PER 10배) 가정 시의 이론적 적정주가
        
        val_html = f"""
        <div style='background-color: #f8fafc; padding: 20px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px;'>
            <h5 style='color: #1e40af; margin-top: 0; font-size: 1.15rem;'>💡 한눈에 이해하는 가치 평가 (Valuation)</h5>
            <ul style='line-height: 1.8; font-size: 1.05rem; margin-bottom: 15px;'>
                <li><b>현재 주가:</b> ₩{curr_price:,.0f}</li>
                <li><b style='color:#0f172a;'>EPS (주당순이익):</b> ₩{eps:,.0f} <br><span style='color: #64748b; font-size: 0.95rem;'>👉 <b>쉽게 말해:</b> 이 회사가 1주당 벌어들인 실제 '순수익'입니다. (이 숫자가 클수록 우량한 기업입니다.)</span></li>
                <li><b style='color:#0f172a;'>PER (주가수익비율):</b> {per:.2f}배 <br><span style='color: #64748b; font-size: 0.95rem;'>👉 <b>쉽게 말해:</b> 내가 투자한 원금을 이 회사의 순수익만으로 모두 회수하는 데 걸리는 시간(년)입니다. (보통 10배 이하를 저평가로 봅니다.)</span></li>
            </ul>
            <div style='background-color: #ffffff; padding: 15px; border-radius: 8px; border: 1px dashed #cbd5e1;'>
                <h5 style='color: #0f172a; margin-top:0;'>🎯 이론적 적정주가 계산기</h5>
                <p style='margin:0;'>만약 이 회사가 대한민국 주식시장 평균 수준(PER 10배)의 대우를 받는다고 가정하면?</p>
                <p style='font-size: 1.2rem; margin-top: 10px; margin-bottom: 5px;'><b>이론적 적정주가:</b> ₩{eps:,.0f} (EPS) × 10배 (PER) = <b style='color: #22c55e;'>₩{fair_value:,.0f}</b></p>
                <p style='font-size: 0.9rem; color:#64748b; margin:0;'>(이론 가격보다 현재 주가가 높다면 미래 성장 기대감이 반영된 것이고, 낮다면 저평가 구간일 수 있습니다.)</p>
            </div>
        """
        if target_price > 0:
            val_html += f"<p style='margin-top:15px; font-size:1.1rem;'><b>📈 증권사 평균 목표주가:</b> <b style='color: #ef4444;'>₩{target_price:,.0f}</b></p>"
        val_html += "</div>"
        valuation_html = val_html
        
        # 3. 분기/연간 실적 표 크롤링
        try:
            cop_table = soup.select_one('div.cop_analysis table')
            if cop_table:
                ths = cop_table.select('thead tr:nth-child(2) th')
                dates = [th.text.strip() for th in ths][-4:] # 최근 4개 데이터만
                
                tbody_trs = cop_table.select('tbody tr')
                rev_tds = [td.text.strip() for td in tbody_trs[0].select('td')][-4:] # 매출액
                op_tds = [td.text.strip() for td in tbody_trs[1].select('td')][-4:]  # 영업이익
                net_tds = [td.text.strip() for td in tbody_trs[2].select('td')][-4:] # 당기순이익
                
                html = "<table class='ma-table'><tr><th>구분</th>"
                for d in dates: html += f"<th>{d}</th>"
                html += "</tr>"
                html += f"<tr><td><b>매출액(억원)</b></td>{''.join([f'<td>{v}</td>' for v in rev_tds])}</tr>"
                html += f"<tr><td><b>영업이익(억원)</b></td>{''.join([f'<td>{v}</td>' for v in op_tds])}</tr>"
                html += f"<tr><td><b>당기순이익(억원)</b></td>{''.join([f'<td>{v}</td>' for v in net_tds])}</tr>"
                html += "</table><p style='font-size: 0.85rem; color: #666; margin-top: 5px;'>* (E) 표시는 증권사 추정치입니다. 출처: 네이버 금융</p>"
                earnings_html = html
        except: pass
            
    except Exception as e:
        pass
        
    return company_name, market_cap_usd, valuation_html, earnings_html

def fetch_investing_news(ticker, company_name=""):
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

def get_detailed_earnings_with_impact(ticker_symbol, df_1d):
    """한국 시간(KST) 변환 및 발표 직후 주가 반응을 포함한 완벽한 실적 표 생성"""
    earnings_html = ""
    try:
        tkr = yf.Ticker(ticker_symbol)
        earn_df = tkr.get_earnings_dates(limit=8)
        
        if earn_df is not None and not earn_df.empty:
            # 💡 핵심: UTC 시간을 한국 시간(KST)으로 완벽하게 변환
            earn_df.index = earn_df.index.tz_convert('Asia/Seoul')
            
            rows = []
            for dt, row in earn_df.iterrows():
                # 예상치와 실제치가 모두 NaN이면 미래 데이터거나 쓰레기값이므로 스킵
                if pd.isna(row.get('EPS Estimate')) and pd.isna(row.get('Reported EPS')):
                    continue
                    
                dt_str = dt.strftime('%Y-%m-%d %H:%M')
                est = row.get('EPS Estimate', pd.NA)
                act = row.get('Reported EPS', pd.NA)
                surp = row.get('Surprise(%)', pd.NA)
                
                est_str = f"{est:.2f}" if pd.notna(est) else "-"
                act_str = f"{act:.2f}" if pd.notna(act) else "-"
                
                surp_str = "-"
                if pd.notna(surp):
                    s_val = surp * 100
                    color = "#22c55e" if s_val > 0 else "#ef4444"
                    surp_str = f"<span style='color:{color}; font-weight:bold;'>{s_val:+.1f}%</span>"
                    
                # 💡 주가 반응(Impact) 계산: 실적 발표일 당시의 등락률 추적
                impact_str = "-"
                date_only = dt.strftime('%Y-%m-%d')
                if not df_1d.empty:
                    df_1d_dates = df_1d.index.strftime('%Y-%m-%d')
                    if date_only in df_1d_dates:
                        target_idx = df_1d.index[df_1d_dates == date_only][0]
                        pct = df_1d.loc[target_idx, 'Pct_Change']
                        c = "#22c55e" if pct > 0 else "#ef4444"
                        impact_str = f"<span style='color:{c}; font-weight:bold;'>{pct:+.2f}%</span>"
                    else:
                        # 장 마감 후 발표거나 휴일이면 최대 3일 뒤의 거래일 반응 확인
                        for i in range(1, 4):
                            next_day = (dt + pd.Timedelta(days=i)).strftime('%Y-%m-%d')
                            if next_day in df_1d_dates:
                                target_idx = df_1d.index[df_1d_dates == next_day][0]
                                pct = df_1d.loc[target_idx, 'Pct_Change']
                                c = "#22c55e" if pct > 0 else "#ef4444"
                                impact_str = f"<span style='color:{c}; font-weight:bold;'>{pct:+.2f}% (직후 거래일)</span>"
                                break
                
                rows.append(f"<tr><td>{dt_str}</td><td>{est_str}</td><td>{act_str}</td><td>{surp_str}</td><td>{impact_str}</td></tr>")
            
            if rows:
                earnings_html = f"<table class='ma-table'><tr><th>발표 일시 (한국시간)</th><th>예상 EPS</th><th>실측 EPS</th><th>서프라이즈 (차이)</th><th>발표 직후 주가 반응</th></tr>"
                earnings_html += "".join(rows) + "</table>"
    except:
        pass
        
    return earnings_html

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
        
        val_html = f"""
        <div style='background-color: #f8fafc; padding: 20px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px;'>
            <h5 style='color: #1e40af; margin-top: 0; font-size: 1.15rem;'>💡 한눈에 이해하는 가치 평가 (Valuation)</h5>
            <ul style='line-height: 1.8; font-size: 1.05rem; margin-bottom: 15px;'>
                <li><b>현재 주가:</b> ${curr_price:.2f}</li>
                <li><b style='color:#0f172a;'>현재 EPS (주당순이익):</b> ${trailing_eps:.2f} <br><span style='color: #64748b; font-size: 0.95rem;'>👉 이 회사가 1주당 벌어들인 실제 '순수익'입니다.</span></li>
                <li><b style='color:#0f172a;'>내년 예상 EPS:</b> ${forward_eps:.2f}</li>
                <li><b style='color:#0f172a;'>현재 PER (주가수익비율):</b> {trailing_pe:.2f}배 <br><span style='color: #64748b; font-size: 0.95rem;'>👉 현재 벌어들이는 수익(EPS) 대비 주가가 몇 배로 평가받고 있는지 나타냅니다.</span></li>
            </ul>
        """
        if calc_forward_price:
            color = "#22c55e" if calc_forward_price > curr_price else "#ef4444"
            val_html += f"""
            <div style='background-color: #ffffff; padding: 15px; border-radius: 8px; border: 1px dashed #cbd5e1;'>
                <h5 style='color: #0f172a; margin-top:0;'>🎯 이론적 기대 적정주가 계산기</h5>
                <p style='margin:0;'>만약 이 회사가 내년에도 현재의 프리미엄(PER)을 유지한다고 가정하면?</p>
                <p style='font-size: 1.2rem; margin-top: 10px; margin-bottom: 5px;'><b>기대 적정주가:</b> ${forward_eps:.2f} (내년 EPS) × {trailing_pe:.2f}배 (현재 PER) = <b style='color: {color};'>${calc_forward_price:.2f}</b></p>
            </div>
            """
        if target_price > 0:
            val_html += f"<p style='margin-top:15px; font-size:1.1rem;'><b>📈 월가 애널리스트 평균 목표주가:</b> <b style='color: #ef4444;'>${target_price:.2f}</b></p>"
        val_html += "</div>"
        
        return val_html
    except Exception as e:
        return "<p style='color:#ef4444;'>가치 평가 데이터를 불러올 수 없습니다. (야후 파이낸스 접속량 제한 방어됨)</p>"

def parse_yf_df(raw_df):
    if raw_df.empty: return pd.DataFrame(columns=['Open', 'Close'])
    if isinstance(raw_df.columns, pd.MultiIndex):
        try:
            return pd.DataFrame({'Open': raw_df['Open'].iloc[:, 0], 'Close': raw_df['Close'].iloc[:, 0]})
        except: pass
    return raw_df[['Open', 'Close']]

def fetch_financial_data(ticker_symbol):
    if ticker_symbol.isdigit(): ticker_symbol = f"{ticker_symbol}.KS"
    is_korean = ticker_symbol.endswith('.KS') or ticker_symbol.endswith('.KQ')
    benchmark_ticker = "^KS11" if is_korean else "^IXIC" 
    benchmark_name = "코스피(KOSPI)" if is_korean else "나스닥(NASDAQ)"

    company_name = ""
    market_cap = 0.0
    valuation_html = ""
    earnings_html = ""
    
    if is_korean:
        # 한국 종목은 네이버 크롤링으로 완벽 커버 (적정주가, 실적 포함)
        company_name, market_cap, valuation_html, earnings_html = get_korean_stock_info(ticker_symbol)
    else:
        try:
            tkr = yf.Ticker(ticker_symbol)
            company_name = tkr.info.get('longName', tkr.info.get('shortName', ''))
            market_cap = tkr.info.get('marketCap', 0.0)
            valuation_html = get_valuation_html(ticker_symbol)
        except: pass

    for attempt in range(3):
        try:
            df_1d_raw = yf.download(ticker_symbol, period="2y", interval="1d", progress=False)
            df_1h_raw = yf.download(ticker_symbol, period="1y", interval="1h", progress=False)
            bm_raw = yf.download(benchmark_ticker, period="2y", interval="1d", progress=False)
            
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
            
            # 미국 주식일 경우 완벽한 실적 표(한국시간 + 주가반응) 생성
            if not is_korean:
                us_earnings = get_detailed_earnings_with_impact(ticker_symbol, df_1d)
                if us_earnings: earnings_html = us_earnings
                else: earnings_html = "<p style='color:#ef4444;'>해당 종목의 분기 실적 데이터를 불러올 수 없거나 제공되지 않습니다.</p>"
            
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
