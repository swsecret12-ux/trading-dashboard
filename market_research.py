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
        # 💡 "Partnership" 등 핵심 호재를 잡아내도록 검색어 강화
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

        # 일봉 데이터 로드 (5년치 로드하여 실적일 주가 계산에 활용)
        hist_1d = ticker.history(period="5y")
        if hist_1d.empty: return {"error": "차트 데이터를 불러올 수 없습니다."}
        
        current_price = float(hist_1d['Close'].iloc[-1])
        current_vol = int(hist_1d['Volume'].iloc[-1])
        
        # 💡 예쁘고 직관적인 모멘텀 표 데이터 생성 로직
        def calc_return_html(days):
            if len(hist_1d) > days:
                past = float(hist_1d['Close'].iloc[-(days+1)])
                pct = ((current_price - past)/past)*100
                color = "#ef4444" if pct < 0 else "#22c55e" # 빨강 or 초록
                sign = "+" if pct > 0 else ""
                return f"${past:.2f} ➔ ${current_price:.2f}", f"<span style='color:{color}; font-weight:bold;'>{sign}{pct:.2f}%</span>"
            return "-", "-"
        
        v1_p, v1_pct = calc_return_html(1)
        v1w_p, v1w_pct = calc_return_html(5)
        v1m_p, v1m_pct = calc_return_html(20)
        v1q_p, v1q_pct = calc_return_html(60)
        v1y_p, v1y_pct = calc_return_html(250)

        # 💡 MA -> EMA (지수이동평균) 200선으로 완벽 변경
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

        # 💡 실적 발표일 주가 등락률 계산 함수
        def get_earnings_price_change(target_date_str):
            try:
                target_date = pd.to_datetime(target_date_str)
                if hist_1d.index.tz is not None:
                    target_date = target_date.tz_localize(hist_1d.index.tz) if target_date.tzinfo is None else target_date.tz_convert(hist_1d.index.tz)
                
                # 해당 날짜와 가장 가까운 인덱스 찾기
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

        # 💡 3개년 (12분기) 실적 데이터 및 디자인 포맷팅
        earnings_html = ""
        try:
            # EPS라는 어려운 용어 대신 '시장 예상치'와 '실제 발표치'로 명칭 변경 및 3년(12분기) 제한
            edts = ticker.get_earnings_dates(limit=12)
            if edts is not None and not edts.empty:
                edts = edts.reset_index()
                edts['Date'] = edts['Earnings Date'].dt.strftime('%Y-%m-%d')
                
                edts_table = """
                <table class='ma-table' style='text-align:center;'>
                  <tr style='background-color:#f1f5f9;'>
                    <th>발표일 (분기)</th><th>시장 예상치</th><th>실제 발표치</th><th>서프라이즈</th><th>발표일 주가 등락</th>
                  </tr>
                """
                for _, row in edts.iterrows():
                    eps_est = row['EPS Estimate']
                    eps_rep = row['Reported EPS']
                    
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
        except:
            earnings_html = "<p>실적 데이터를 불러올 수 없습니다.</p>"

        # 뉴스
        news = ticker.news
        yh_news = "\n".join([f"- {n.get('title','')}" for n in news[:3]]) if news else ""
        inv_news = fetch_investing_news(ticker_symbol)
        raw_news = f"[Yahoo News]\n{yh_news}\n\n[Global Web News]\n{inv_news}"

        # 💡 HTML 뷰 구성
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
    
    # 💡 AI 리포트 분량 및 깊이 3배 강화 프롬프트! (아마존, 매크로 등 팩트 기반)
    prompt = f"""
    당신은 월스트리트의 최정상급 기관 수석 애널리스트입니다. 미사여구(예: ~할 것으로 보입니다, 마법 같은 등)와 감정적인 표현은 철저히 배제하고, 오직 데이터와 팩트 기반의 건조한(Dry) 문체로 보고서를 작성하세요.
    
    **[중요 지시사항]: 일반적인 요약을 넘어, 실제 기관 투자자들이 중요하게 보는 거시경제(매크로) 흐름, 밸류체인 파급력, 향후 가이던스 등을 포함하여 분량을 기존보다 3배 이상 길고 심층적으로 작성하십시오. 단순 숫자 나열은 절대 금지합니다.**
    
    보고서 작성 기준일: {today_str}

    [분석 대상 데이터]
    - 종목명: {ticker} (섹터: {sector})
    - 시가총액: {fin_data.get('market_cap')}
    - 최신 글로벌 뉴스(협업, 실적 등 포함): {fin_data.get('raw_news')}
    - SaveTicker 등 외부 수집 뉴스: {saveticker_text}
    - 유저 메모: {user_input}
    
    [작성 목차 및 필수 포함 내용]
    1. 🏢 시장 위치 및 밸류체인 심층 분석
       - 이 종목이 글로벌 {sector} 섹터 내에서 시가총액 기준으로 어느 정도 위치에 있는지 평가.
       - 단순히 회사를 소개하는 것을 넘어, 주요 경쟁사 및 연계된 공급망(밸류체인) 주식들과의 커플링/디커플링 동향을 심층 분석.
    2. 🌍 매크로 동향 및 핵심 뉴스 팩트체크 (가장 중요)
       - 제공된 뉴스(특히 대형 기업과의 파트너십, M&A, 신제품 발표 등)가 펀더멘털과 향후 매출에 미치는 실제 파급력을 분석. (예: 협업 뉴스가 있다면 그 이유와 향후 수익 기여도 전망 등).
       - 현재 금리 인상/인하 기조나 섹터 전반의 매크로 환경이 해당 종목의 투심에 미치는 영향을 구체적으로 서술.
    3. 💰 실적(Earnings) 및 모멘텀 종합 의견
       - 최근 3개년 실적 상회/하회 트렌드가 시장에 어떤 시그널을 주었는지 분석.
       - 다음 가이던스에 대한 월가 기관들의 시각과 우려/기대감을 추론하여 기재.
    4. 💡 기관 트레이딩 결론 (Actionable Insight)
       - 펀더멘털, 매크로, 뉴스 모멘텀을 모두 종합하여, 현재 포지션 진입(신규 Long/Short/관망)에 대한 구체적이고 냉철한 조언. 리스크 관리 측면도 반드시 포함.
    """
    return ask_gemini_dynamic(prompt, [])
