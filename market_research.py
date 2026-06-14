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
        query = urllib.parse.quote(f"{ticker} stock OR partnership OR earnings")
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
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        market_cap = info.get('marketCap', 0)
        if market_cap > 1e12: mcap_str = f"{market_cap / 1e12:.2f}T (조 달러)"
        elif market_cap > 1e9: mcap_str = f"{market_cap / 1e9:.2f}B (십억 달러)"
        elif market_cap > 1e6: mcap_str = f"{market_cap / 1e6:.2f}M (백만 달러)"
        else: mcap_str = "데이터 없음"

        hist_1d = ticker.history(period="5y")
        if hist_1d.empty: return {"error": "차트 데이터를 불러올 수 없습니다."}
        
        current_price = float(hist_1d['Close'].iloc[-1])
        current_vol = int(hist_1d['Volume'].iloc[-1])
        
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

        # 💡 미래 날짜 실적 등락률 오류 방지 로직 추가
        def get_earnings_price_change(target_date_str):
            try:
                target_date = pd.to_datetime(target_date_str)
                # 아직 오지 않은 미래 날짜면 계산 생략
                if target_date > pd.Timestamp.now().normalize():
                    return "-"
                    
                if hist_1d.index.tz is not None:
                    target_date = target_date.tz_localize(hist_1d.index.tz) if target_date.tzinfo is None else target_date.tz_convert(hist_1d.index.tz)
                
                idx = hist_1d.index.get_indexer([target_date], method='nearest')[0]
                start_idx = max(0, idx - 1)
                end_idx = min(len(hist_1d) - 1, idx + 1)
                
                start_p = hist_1d['Close'].iloc[start_idx]
                end_p = hist_1d['Close'].iloc[end_idx]
                pct = ((end_p - start_p) / start_p) * 100
                color = "#ef4444" if pct < 0 else "#22c55e"
                sign = "+" if pct > 0 else ""
                return f"<span style='color:{color}; font-weight:bold;'>{sign}{pct:.1f}%</span><br><span style='font-size:0.8rem; color:#888;'>(${start_p:.2f} ➔ ${end_p:.2f})</span>"
            except:
                return "-"

        earnings_html = ""
        try:
            edts = ticker.get_earnings_dates(limit=12)
            if edts is not None and not edts.empty:
                edts = edts.reset_index()
                date_col = 'Earnings Date' if 'Earnings Date' in edts.columns else edts.columns[0]
                
                if edts[date_col].dt.tz is not None:
                    edts[date_col] = edts[date_col].dt.tz_convert('US/Eastern')
                else:
                    edts[date_col] = edts[date_col].dt.tz_localize('UTC').dt.tz_convert('US/Eastern')
                
                edts['Date'] = edts[date_col].dt.strftime('%Y-%m-%d')
                
                edts_table = """
                <table class='ma-table' style='text-align:center;'>
                  <tr style='background-color:#f1f5f9;'>
                    <th>발표일 (분기)</th><th>시장 예상치</th><th>실제 발표치</th><th>서프라이즈</th><th>발표일 주가 등락</th>
                  </tr>
                """
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
                        
                    price_chg_html = get_earnings_price_change(row['Date'])
                    edts_table += f"<tr><td><b>{row['Date']}</b></td><td>{est_str}</td><td>{rep_str}</td><td>{surprise_html}</td><td>{price_chg_html}</td></tr>"
                edts_table += "</table>"
                earnings_html = edts_table
            else:
                earnings_html = "<p>최근 실적 데이터가 없습니다.</p>"
        except Exception as e:
            earnings_html = f"<p>실적 데이터 오류: {str(e)}</p>"

        news = ticker.news
        yh_news = "\n".join([f"- {n.get('title','')}" for n in news[:3]]) if news else ""
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
            "last_cross_type": cross_type, "last_cross_date": cross_date
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input="", saveticker_text=""):
    from api_utils import ask_gemini_dynamic
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    # 💡 장황함 제거, 순서 변경, 10% 급변동 표 지시 추가
    prompt = f"""
    당신은 월스트리트의 핵심 기관 애널리스트입니다. 수식어와 장황한 설명을 절대 금지하며, 철저히 '개조식(Bullet points)'과 '핵심 요약' 위주로 간결하게 작성하세요.
    보고서 작성 기준일: {today_str}

    [분석 대상 데이터]
    - 종목명: {ticker} (섹터: {sector})
    - 시가총액: {fin_data.get('market_cap')}
    - 최신 글로벌 뉴스(협업, 실적 등 포함): {fin_data.get('raw_news')}
    - SaveTicker 등 외부 수집 뉴스: {saveticker_text}
    - 유저 메모: {user_input}
    
    [작성 목차 및 필수 지시사항]
    1. 🏢 시장 위치 및 밸류체인
       - 시가총액 기준 섹터 내 위치 단답형 요약.
       - 주요 경쟁사 및 연계 밸류체인(공급망) 주식 나열.
    2. 💰 실적(Earnings) 종합 의견
       - 최근 실적발표 상회/하회 여부가 주가에 미친 영향 2줄 이내 요약.
    3. 📈 가격 및 거래량 모멘텀 분석
       - 현재 추세 상태 간략 진단.
    4. 🚨 [최근 급변동 사유 분석] (조건부 작성)
       - 제공된 데이터 상 1개월 또는 1분기 변동성이 +10% 이상이거나 -10% 이하인 경우에만 이 항목을 표(Table) 형태로 작성하세요.
       - 표의 컬럼은 [이슈 발생일(추정) | 관련 파트너십/실적 뉴스 내용 | 주가에 미친 파급력] 으로 구성하세요. (예: SNOW-아마존 협업 등 팩트 기재)
    5. 💡 기관 트레이딩 결론
       - 명확한 포지션(Long/Short/관망) 단답형 제시 및 핵심 리스크 1줄 요약.
    """
    return ask_gemini_dynamic(prompt, [])
