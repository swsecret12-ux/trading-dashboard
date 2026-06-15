import yfinance as yf
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse
import xml.etree.ElementTree as ET

def fetch_investing_news(ticker):
    """구글 뉴스 RSS를 우회하여 최신 글로벌 기사(Investing, 파트너십 등)를 긁어옵니다."""
    try:
        query = urllib.parse.quote(f"{ticker} stock OR news")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news_items = []
        for item in root.findall('.//item')[:4]:
            title = item.find('title').text
            pubDate = item.find('pubDate').text
            news_items.append(f"- {title} ({pubDate})")
        return "\n".join(news_items) if news_items else "관련 글로벌 뉴스가 없습니다."
    except:
        return "글로벌 뉴스 수집 실패"

def fetch_saveticker_news(user_id, password):
    """SaveTicker 자동 로그인 및 최신 뉴스 크롤링 (실패 시 빠른 패스)"""
    if not user_id or not password:
        return "SaveTicker 계정 정보가 없습니다."
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        
        login_url = "https://www.saveticker.com/api/auth/callback/credentials"
        session.post(login_url, data={"email": user_id, "password": password}, timeout=5)
        
        res = session.get("https://www.saveticker.com/news", timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all(['p', 'article'])
        text = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
        
        if not text: return "SaveTicker 뉴스 본문 추출 실패"
        return f"[SaveTicker 요약]\n{text[:2500]}"
    except Exception as e:
        return f"SaveTicker 크롤링 에러: {str(e)}"

def fetch_financial_data(ticker_symbol):
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        
        ticker = yf.Ticker(ticker_symbol, session=session)
        
        try: mcap_usd = ticker.fast_info['marketCap']
        except: mcap_usd = 0

        hist_1d = ticker.history(period="5y")
        if hist_1d.empty: return {"error": "차트 데이터를 불러올 수 없습니다."}
        
        current_price = float(hist_1d['Close'].iloc[-1])
        
        def calc_return_html(days):
            if len(hist_1d) > days:
                past = float(hist_1d['Close'].iloc[-(days+1)])
                pct = ((current_price - past)/past)*100
                color = "#ef4444" if pct < 0 else "#22c55e" 
                sign = "+" if pct > 0 else ""
                return f"${past:.2f} ➔ ${current_price:.2f}", f"<span style='color:{color}; font-weight:bold;'>{sign}{pct:.2f}%</span>"
            return "-", "-"
        
        v1_p, v1_pct = calc_return_html(1)
        v1w_p, v1w_pct = calc_return_html(5)
        v1m_p, v1m_pct = calc_return_html(20)
        v1q_p, v1q_pct = calc_return_html(60)
        v1y_p, v1y_pct = calc_return_html(250)

        hist_1d['EMA200_1D'] = hist_1d['Close'].ewm(span=200, adjust=False).mean()
        
        hist_1h = ticker.history(period="730d", interval="1h")
        if not hist_1h.empty:
            hist_4h = hist_1h.resample('4h').agg({'Close': 'last'}).dropna()
            hist_4h['EMA200_4H'] = hist_4h['Close'].ewm(span=200, adjust=False).mean()
            
            if hist_1d.index.tz is None: hist_1d.index = hist_1d.index.tz_localize('UTC')
            if hist_4h.index.tz is None: hist_4h.index = hist_4h.index.tz_localize('UTC')
            
            df_1d_ma = hist_1d[['EMA200_1D']].dropna().sort_index()
            df_4h_ma = hist_4h[['EMA200_4H', 'Close']].dropna().sort_index()
            
            # UTC 강제 통일 병합
            merged = pd.merge_asof(df_4h_ma, df_1d_ma, left_index=True, right_index=True, direction='backward').dropna()
            
            merged['Prev_4H'] = merged['EMA200_4H'].shift(1)
            merged['Prev_1D'] = merged['EMA200_1D'].shift(1)
            
            gc = merged[(merged['EMA200_4H'] > merged['EMA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
            dc = merged[(merged['EMA200_4H'] < merged['EMA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])]
            
            if not gc.empty or not dc.empty:
                last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize('UTC')
                last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize('UTC')
                latest_idx = max(last_gc, last_dc)
                cross_type = "🟢 골든크로스" if latest_idx == last_gc else "🔴 데드크로스"
                cross_date = latest_idx.strftime('%Y-%m-%d %H:%M')
                cross_price = f"${merged.loc[latest_idx, 'Close']:.2f}"
            else:
                cross_type, cross_date, cross_price = "최근 1년 내 크로스 없음", "-", "-"
            
            curr_4h_ema200 = f"${merged['EMA200_4H'].iloc[-1]:.2f}"
            curr_1d_ema200 = f"${merged['EMA200_1D'].iloc[-1]:.2f}"
        else:
            cross_type, cross_date, cross_price = "4H 데이터 로드 불가", "-", "-"
            curr_4h_ema200 = "-"
            curr_1d_ema200 = f"${hist_1d['EMA200_1D'].iloc[-1]:.2f}" if not pd.isna(hist_1d['EMA200_1D'].iloc[-1]) else "-"

        # 💡 최근 2달 이내 10% 이상 급변동 날짜 및 나스닥 등락률 추적 로직 추가
        volatility_events = []
        try:
            recent_hist = hist_1d.tail(60) 
            try: 
                ndx_hist = yf.Ticker("^IXIC", session=session).history(period="1y")
                if ndx_hist.index.tz is None: ndx_hist.index = ndx_hist.index.tz_localize('UTC')
                else: ndx_hist.index = ndx_hist.index.tz_convert('UTC')
            except: 
                ndx_hist = pd.DataFrame()
            
            for i in range(1, len(recent_hist)):
                prev_c = recent_hist['Close'].iloc[i-1]
                curr_c = recent_hist['Close'].iloc[i]
                pct_change = ((curr_c - prev_c) / prev_c) * 100
                
                if abs(pct_change) >= 10.0:
                    target_d = recent_hist.index[i]
                    date_str = target_d.strftime('%Y-%m-%d')
                    ndx_pct_str = "확인불가"
                    
                    if not ndx_hist.empty:
                        try:
                            target_d_utc = target_d.tz_convert('UTC') if target_d.tz is not None else target_d.tz_localize('UTC')
                            idx_arr = ndx_hist.index.get_indexer([target_d_utc], method='nearest')
                            if len(idx_arr) > 0 and idx_arr[0] > 0:
                                n_idx = idx_arr[0]
                                n_prev = ndx_hist['Close'].iloc[n_idx-1]
                                n_curr = ndx_hist['Close'].iloc[n_idx]
                                ndx_pct_str = f"{((n_curr - n_prev) / n_prev) * 100:+.1f}%"
                        except: pass
                    volatility_events.append(f"- 날짜: {date_str} | 종목등락: {pct_change:+.1f}% (${prev_c:.2f}->${curr_c:.2f}) | 나스닥등락: {ndx_pct_str}")
        except: pass
        vol_text = "\n".join(volatility_events) if volatility_events else "최근 2개월 내 10% 이상 일일 급변동 없음."

        # 💡 실적 발표 데이터 (lxml 에러 방어 및 미래/과거 시각적 분리 적용)
        def get_earnings_price_change_safe(target_date_str):
            current_date_str = datetime.today().strftime('%Y-%m-%d')
            if target_date_str > current_date_str: return "-"
            try:
                target_dt = pd.to_datetime(target_date_str)
                if hist_1d.index.tz is not None:
                    target_dt = target_dt.tz_localize(hist_1d.index.tz) if target_dt.tzinfo is None else target_dt.tz_convert(hist_1d.index.tz)
                idx_arr = hist_1d.index.get_indexer([target_dt], method='nearest')
                if len(idx_arr) > 0 and idx_arr[0] >= 0:
                    idx = idx_arr[0]
                    start_idx = max(0, idx - 1)
                    end_idx = min(len(hist_1d) - 1, idx + 1)
                    start_p = hist_1d['Close'].iloc[start_idx]
                    end_p = hist_1d['Close'].iloc[end_idx]
                    pct = ((end_p - start_p) / start_p) * 100
                    color = "#ef4444" if pct < 0 else "#22c55e"
                    sign = "+" if pct > 0 else ""
                    return f"<span style='color:{color}; font-weight:bold;'>{sign}{pct:.1f}%</span><br><span style='font-size:0.8rem; color:#888;'>(${start_p:.2f} ➔ ${end_p:.2f})</span>"
            except: return "-"
            return "-"

        earnings_html = ""
        try:
            # lxml 에러 방지를 위해 broad catch 적용
            try: edts = ticker.get_earnings_dates(limit=12)
            except Exception as internal_e: 
                if "lxml" in str(internal_e).lower() or "html5lib" in str(internal_e).lower():
                    raise ValueError("lxml_missing")
                edts = ticker.earnings_dates
                if edts is not None: edts = edts.head(12)
                
            if edts is not None and not edts.empty:
                edts = edts.reset_index()
                date_col = 'Earnings Date' if 'Earnings Date' in edts.columns else edts.columns[0]
                
                # 강제 문자열 슬라이싱으로 타임존 에러 완벽 회피
                edts['Date'] = edts[date_col].astype(str).str[:10]
                
                edts_table = """
                <table class='ma-table' style='text-align:center;'>
                  <tr style='background-color:#f1f5f9;'>
                    <th>발표일 (분기)</th><th>시장 예상치</th><th>실제 발표치</th><th>서프라이즈</th><th>발표일 주가 등락</th>
                  </tr>
                """
                current_date_str = datetime.today().strftime('%Y-%m-%d')
                
                for _, row in edts.iterrows():
                    eps_est = row.get('EPS Estimate', None)
                    eps_rep = row.get('Reported EPS', None)
                    est_str = f"{eps_est:.2f}" if pd.notna(eps_est) else "-"
                    rep_str = f"{eps_rep:.2f}" if pd.notna(eps_rep) else "-"
                    
                    surprise_html = "-"
                    if pd.notna(eps_est) and pd.notna(eps_rep) and eps_est != 0:
                        surp_pct = ((eps_rep - eps_est) / abs(eps_est)) * 100
                        scolor = "#ef4444" if surp_pct < 0 else "#22c55e"
                        ssign = "+" if surp_pct > 0 else ""
                        stxt = "상회" if surp_pct > 0 else "하회"
                        surprise_html = f"<span style='color:{scolor}; font-weight:bold;'>{ssign}{surp_pct:.1f}% {stxt}</span>"
                        
                    price_chg_html = get_earnings_price_change_safe(row['Date'])
                    
                    # 미래 실적발표일 강조 디자인 적용
                    row_bg = "background-color: #fffbeb;" if row['Date'] > current_date_str else ""
                    date_icon = "⏳ " if row['Date'] > current_date_str else ""
                    
                    edts_table += f"<tr style='{row_bg}'><td><b>{date_icon}{row['Date']}</b></td><td>{est_str}</td><td>{rep_str}</td><td>{surprise_html}</td><td>{price_chg_html}</td></tr>"
                edts_table += "</table>"
                earnings_html = edts_table
            else: earnings_html = "<p>최근 실적 데이터를 불러올 수 없습니다.</p>"
        except ValueError as ve:
            if str(ve) == "lxml_missing":
                earnings_html = "<p style='color:#ef4444;'>⚠️ 실적 표 생성 불가: 서버에 lxml 패키지가 설치되지 않아 데이터를 가져올 수 없습니다.</p>"
        except Exception as e: earnings_html = f"<p>실적 데이터 오류: {str(e)}</p>"

        try:
            news = ticker.news
            yh_news_list = []
            for n in news[:5]:
                title = n.get('title', '')
                if not title and 'content' in n: title = n['content'].get('title', '')
                if title: yh_news_list.append(f"- {title}")
            yh_news = "\n".join(yh_news_list) if yh_news_list else "최근 야후 뉴스를 불러올 수 없습니다."
        except: yh_news = "야후 뉴스 제공 오류"
            
        inv_news = fetch_investing_news(ticker_symbol)
        raw_news = f"[Yahoo News]\n{yh_news}\n\n[Global Web News]\n{inv_news}"

        ma_html = f"""
        <table class="ma-table">
          <tr style='background-color:#f1f5f9;'><th>지표 (EMA 기준)</th><th>상태 / 가격</th><th>발생일</th></tr>
          <tr><td><b>EMA 4H/1D 크로스</b></td><td style='font-size:1.1rem; font-weight:bold;'>{cross_type}</td><td>{cross_date}</td></tr>
          <tr><td><b>크로스 당시 주가</b></td><td>{cross_price}</td><td>-</td></tr>
          <tr><td><b>현재 4시간봉 EMA 200</b></td><td>{curr_4h_ema200}</td><td>-</td></tr>
          <tr><td><b>현재 1일봉 EMA 200</b></td><td>{curr_1d_ema200}</td><td>-</td></tr>
        </table>
        """
        
        mom_html = f"""
        <table class="ma-table" style='text-align:center;'>
          <tr style='background-color:#f1f5f9;'><th>기간</th><th>과거 ➔ 현재</th><th>주가 변동률</th></tr>
          <tr><td><b>1일</b></td><td>{v1_p}</td><td>{v1_pct}</td></tr>
          <tr><td><b>1주일</b></td><td>{v1w_p}</td><td>{v1w_pct}</td></tr>
          <tr><td><b>1개월</b></td><td>{v1m_p}</td><td>{v1m_pct}</td></tr>
          <tr><td><b>1분기</b></td><td>{v1q_p}</td><td>{v1q_pct}</td></tr>
          <tr><td><b>1년</b></td><td>{v1y_p}</td><td>{v1y_pct}</td></tr>
        </table>
        """

        return {
            "market_cap": mcap_usd, "raw_news": raw_news, "ma_html": ma_html, 
            "momentum_html": mom_html, "earnings_html": earnings_html,
            "last_cross_type": cross_type, "last_cross_date": cross_date,
            "vol_events_text": vol_text
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input="", saveticker_text=""):
    from api_utils import ask_gemini_dynamic
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    prompt = f"""
    당신은 월스트리트의 최정상급 기관 수석 애널리스트입니다. 미사여구를 배제하고 개조식(단답형, 불릿 포인트)으로 명확히 요약하여 작성하세요.
    보고서 작성 기준일: {today_str}

    [분석 대상 데이터]
    - 종목명: {ticker} (섹터: {sector})
    - 최근 2달 내 10% 이상 일일 급변동 팩트 (날짜 / 종목등락 / 당일 나스닥 등락):
    {fin_data.get('vol_events_text')}
    - 최신 글로벌 뉴스: {fin_data.get('raw_news')}
    - 유저 메모: {user_input}
    
    [작성 목차]
    1. 🏢 시장 위치 및 핵심 밸류체인 요약
    
    2. 🚨 최근 10% 이상 급변동 사유 팩트체크 (가장 중요)
       - 위 '일일 급변동 팩트'에 날짜가 존재한다면, 반드시 표(Table)로 만들어서 보여주세요.
       - 열 구성: | 발생 날짜 | 종목 등락률 | 나스닥 지수 등락률 | 구체적 촉매제 (추정 금지, 팩트 기반) |
       - [경고]: 제공된 최신 뉴스에 과거(1~2달 전)의 내용이 없다고 해서 "데이터가 없다"고 변명하지 마십시오! 당신의 방대한 내부 학습 데이터베이스를 총동원하여, 해당 날짜에 해당 기업에 어떤 이벤트(예: 아마존 파트너십 발표, 실적 발표, 금리 이슈 등)가 있었는지 기필코 찾아내어 구체적 촉매제 칸을 채우세요.
       - 만약 팩트 데이터 자체가 없다면 "최근 2개월 내 10% 이상 급변동 없음"이라고 적으세요.
       
    3. 💰 실적(Earnings) 및 모멘텀 종합 의견 (개조식)
    
    4. 💡 기관 트레이딩 결론 (Actionable Insight: 구체적 롱/숏/관망 의견)
    """
    return ask_gemini_dynamic(prompt, [])
