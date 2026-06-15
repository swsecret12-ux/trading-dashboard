import yfinance as yf
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import urllib.parse
import xml.etree.ElementTree as ET

def get_robust_session():
    session = requests.Session()
    # 💡 무한 로딩 원인 제거: 서버 차단 시 10분 넘게 재시도하며 뻗어버리는 로직(Retry)을 과감히 삭제!
    # 실패하면 즉시 실패 처리하여 병목을 막고 쾌적하게 유지합니다.
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })
    return session

def fetch_investing_news(ticker):
    """구글 뉴스 RSS를 우회하여 최신 글로벌 기사를 긁어옵니다."""
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
    """SaveTicker 자동 로그인 및 최신 뉴스 크롤링"""
    if not user_id or not password:
        return "SaveTicker 계정 정보가 없습니다."
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        
        login_url = "https://www.saveticker.com/api/auth/callback/credentials"
        session.post(login_url, data={"email": user_id, "password": password}, timeout=10)
        
        res = session.get("https://www.saveticker.com/news", timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all(['p', 'article'])
        text = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
        
        if not text: return "SaveTicker 뉴스 본문 추출 실패"
        return f"[SaveTicker 요약]\n{text[:2500]}"
    except Exception as e:
        return f"SaveTicker 크롤링 에러: {str(e)}"

def fetch_financial_data(ticker_symbol):
    try:
        session = get_robust_session()
        ticker = yf.Ticker(ticker_symbol, session=session)
        info = ticker.info
        
        market_cap = info.get('marketCap', 0)
        if market_cap > 1e12: mcap_str = f"{market_cap / 1e12:.2f}T (조 달러)"
        elif market_cap > 1e9: mcap_str = f"{market_cap / 1e9:.2f}B (십억 달러)"
        elif market_cap > 1e6: mcap_str = f"{market_cap / 1e6:.2f}M (백만 달러)"
        else: mcap_str = "데이터 없음"

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
            
            merged = pd.merge_asof(df_4h_ma, df_1d_ma, left_index=True, right_index=True, direction='backward')
            merged = merged.dropna()
            
            merged['Prev_4H'] = merged['EMA200_4H'].shift(1)
            merged['Prev_1D'] = merged['EMA200_1D'].shift(1)
            
            gc = merged[(merged['EMA200_4H'] > merged['EMA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
            dc = merged[(merged['EMA200_4H'] < merged['EMA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])]
            
            if not gc.empty or not dc.empty:
                last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize(merged.index.tz)
                last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize(merged.index.tz)
                
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

        earnings_html = ""
        try:
            try:
                edts = ticker.get_earnings_dates(limit=12)
            except Exception:
                edts = ticker.earnings_dates
                if edts is not None: edts = edts.head(12)
                
            if edts is not None and not edts.empty:
                edts = edts.reset_index()
                date_col = 'Earnings Date' if 'Earnings Date' in edts.columns else edts.columns[0]
                
                # 타임존 무시하고 텍스트로 잘라내어 미래 날짜 에러 완벽 차단
                edts['Date'] = edts[date_col].astype(str).str[:10]
                current_date_str = datetime.today().strftime('%Y-%m-%d')
                
                def get_earnings_price_change_safe(target_date_str):
                    if target_date_str > current_date_str: return "-"
                    try:
                        target_dt = pd.to_datetime(target_date_str).tz_localize(hist_1d.index.tz) if hist_1d.index.tz else pd.to_datetime(target_date_str)
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

                edts_table = "<table class='ma-table' style='text-align:center;'><tr style='background-color:#f1f5f9;'><th>발표일 (분기)</th><th>시장 예상치</th><th>실제 발표치</th><th>서프라이즈</th><th>발표일 주가 등락</th></tr>"
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
                    edts_table += f"<tr><td><b>{row['Date']}</b></td><td>{est_str}</td><td>{rep_str}</td><td>{surprise_html}</td><td>{price_chg_html}</td></tr>"
                edts_table += "</table>"
                earnings_html = edts_table
            else: earnings_html = "<p>최근 실적 데이터를 불러올 수 없습니다.</p>"
        except Exception as e: earnings_html = f"<p>실적 데이터 오류: {str(e)}</p>"

        volatility_events = []
        try:
            recent_hist = hist_1d.tail(60) 
            try:
                ndx_hist = yf.Ticker("^IXIC", session=session).history(period="1y")
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
                            target_d_utc = pd.to_datetime(target_d, utc=True)
                            ndx_idx_utc = pd.to_datetime(ndx_hist.index, utc=True)
                            idx_arr = ndx_idx_utc.get_indexer([target_d_utc], method='nearest')
                            if len(idx_arr) > 0 and idx_arr[0] > 0:
                                n_idx = idx_arr[0]
                                n_prev = ndx_hist['Close'].iloc[n_idx-1]
                                n_curr = ndx_hist['Close'].iloc[n_idx]
                                ndx_pct_str = f"{((n_curr - n_prev) / n_prev) * 100:+.1f}%"
                        except: pass
                        
                    volatility_events.append(f"- 날짜: {date_str} | 종목등락: {pct_change:+.1f}% (${prev_c:.2f}->${curr_c:.2f}) | 당일 나스닥등락: {ndx_pct_str}")
        except: pass
        vol_text = "\n".join(volatility_events) if volatility_events else "최근 2개월 내 10% 이상 일일 급변동 없음."

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
            "market_cap": mcap_str, "raw_news": raw_news, "ma_html": ma_html, 
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
    당신은 월스트리트의 최정상급 기관 수석 애널리스트입니다.
    보고서 작성 기준일: {today_str}

    [분석 대상 데이터]
    - 종목명: {ticker} (섹터: {sector})
    - 시가총액: {fin_data.get('market_cap')}
    - 최근 2달 내 10% 이상 일일 급변동 발생일 팩트 (날짜/종목등락/나스닥등락):
    {fin_data.get('vol_events_text')}
    - 최신 글로벌 뉴스(협업, 실적 등 포함): {fin_data.get('raw_news')}
    - 유저 메모: {user_input}
    
    [작성 가이드라인]
    1. 🏢 시장 위치 및 밸류체인 분석
    2. 💰 실적(Earnings) 및 모멘텀 종합 의견
    
    3. 🚨 최근 10% 이상 급변동 사유 분석 (매우 중요)
       - 위 '일일 급변동 발생일 팩트' 데이터가 존재한다면 반드시 표(Table) 포맷으로 작성하세요.
       - 열 구성: | 날짜 | 급등락(종목 변동률) | 나스닥 지수 변동률 | 급변동 촉매제(호재/악재 뉴스 요약) |
       - 제공된 뉴스 내용(아마존 협업, 실적 쇼크 등)과 해당 날짜를 매칭시켜서 구체적인 이유를 반드시 적으세요.
       
    4. 💡 기관 트레이딩 결론 (Actionable Insight)
    """
    return ask_gemini_dynamic(prompt, [])
