import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import urllib.parse
import xml.etree.ElementTree as ET

def fetch_investing_news(ticker):
    """구글 뉴스 RSS를 우회하여 Investing.com의 최신 기사와 파트너십 등 호재를 긁어옵니다."""
    try:
        # 💡 아마존 파트너십 등 거대 호재를 놓치지 않기 위해 검색어에 partnership, earnings 추가!
        query = urllib.parse.quote(f"{ticker} stock news OR partnership OR earnings")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news_items = []
        for item in root.findall('.//item')[:5]:
            title = item.find('title').text
            pubDate = item.find('pubDate').text
            news_items.append(f"- {title} ({pubDate})")
        return "\n".join(news_items) if news_items else "관련 뉴스가 없습니다."
    except:
        return "뉴스 수집 실패"

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
        
        if not text: return "SaveTicker 뉴스 본문 추출 실패 (봇 차단됨)"
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

        hist_1d = ticker.history(period="2y")
        if hist_1d.empty: return {"error": "일봉 차트 데이터를 불러올 수 없습니다."}
        
        current_price = float(hist_1d['Close'].iloc[-1])
        current_vol = int(hist_1d['Volume'].iloc[-1])
        avg_vol_20d = int(hist_1d['Volume'].tail(20).mean())
        
        def calc_return(days):
            if len(hist_1d) > days:
                past = float(hist_1d['Close'].iloc[-(days+1)])
                pct = round(((current_price - past)/past)*100, 2)
                color = "#d32f2f" if pct < 0 else "#2e7d32"
                sign = "+" if pct > 0 else ""
                return f"<span style='font-size:1.05rem;'>${past:.2f} ➔ <b>${current_price:.2f}</b></span> <span style='color:{color}; font-weight:bold;'>({sign}{pct}%)</span>"
            return "-"
        
        vol_1d = calc_return(1)
        vol_1w = calc_return(5)
        vol_1m = calc_return(20)
        vol_1q = calc_return(60)
        vol_1y = calc_return(250)

        hist_1d['MA200_1D'] = hist_1d['Close'].rolling(window=200).mean()
        
        hist_1h = ticker.history(period="730d", interval="1h")
        if not hist_1h.empty:
            hist_4h = hist_1h.resample('4h').agg({'Close': 'last'}).dropna()
            hist_4h['MA200_4H'] = hist_4h['Close'].rolling(window=200).mean()
            
            if hist_1d.index.tz is None: hist_1d.index = hist_1d.index.tz_localize('UTC')
            if hist_4h.index.tz is None: hist_4h.index = hist_4h.index.tz_localize('UTC')
            
            df_1d_ma = hist_1d[['MA200_1D']].dropna().sort_index()
            df_4h_ma = hist_4h[['MA200_4H', 'Close']].dropna().sort_index()
            
            merged = pd.merge_asof(df_4h_ma, df_1d_ma, left_index=True, right_index=True, direction='backward')
            merged = merged.dropna()
            
            merged['Prev_4H'] = merged['MA200_4H'].shift(1)
            merged['Prev_1D'] = merged['MA200_1D'].shift(1)
            
            gc = merged[(merged['MA200_4H'] > merged['MA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
            dc = merged[(merged['MA200_4H'] < merged['MA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])]
            
            if not gc.empty or not dc.empty:
                last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize(merged.index.tz)
                last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize(merged.index.tz)
                
                latest_idx = max(last_gc, last_dc)
                cross_type = "🟢 골든크로스" if latest_idx == last_gc else "🔴 데드크로스"
                cross_date = latest_idx.strftime('%Y-%m-%d %H:%M')
                cross_price = f"${merged.loc[latest_idx, 'Close']:.2f}"
            else:
                cross_type, cross_date, cross_price = "크로스 없음", "-", "-"
            
            curr_4h_ma200 = f"${merged['MA200_4H'].iloc[-1]:.2f}"
            curr_1d_ma200 = f"${merged['MA200_1D'].iloc[-1]:.2f}"
        else:
            cross_type, cross_date, cross_price = "4H 로드 불가", "-", "-"
            curr_4h_ma200 = "-"
            curr_1d_ma200 = f"${hist_1d['MA200_1D'].iloc[-1]:.2f}" if not pd.isna(hist_1d['MA200_1D'].iloc[-1]) else "-"

        earnings_html = ""
        try:
            edts = ticker.get_earnings_dates(limit=6)
            if edts is not None and not edts.empty:
                edts = edts.reset_index()
                edts['Date'] = edts['Earnings Date'].dt.strftime('%Y-%m-%d')
                
                # 가독성 극대화를 위한 프리미엄 테이블 CSS 적용
                edts_table = "<table class='ma-table' style='font-size: 1.05rem; text-align: center;'>"
                edts_table += "<tr style='background-color: #f1f5f9;'><th>발표일</th><th>예상 EPS</th><th>실제 EPS</th><th>서프라이즈</th><th>발표일 주가 등락</th></tr>"
                
                for _, row in edts.iterrows():
                    eps_est = row['EPS Estimate']
                    eps_rep = row['Reported EPS']
                    
                    est_str = f"{eps_est}" if pd.notna(eps_est) else "-"
                    rep_str = f"{eps_rep}" if pd.notna(eps_rep) else "-"
                    
                    surprise_html = "-"
                    if pd.notna(eps_est) and pd.notna(eps_rep) and eps_est != 0:
                        surp_pct = ((eps_rep - eps_est) / abs(eps_est)) * 100
                        color = "#d32f2f" if surp_pct < 0 else "#2e7d32"
                        sign = "+" if surp_pct > 0 else ""
                        icon = "🔴" if surp_pct < 0 else "🟢"
                        surprise_html = f"<span style='color:{color}; font-weight:bold;'>{icon} {sign}{surp_pct:.1f}% {'상회' if surp_pct>0 else '하회'}</span>"
                    
                    # 💡 발표일 당일의 과거 주가 변동률 계산
                    price_change_html = "-"
                    target_date = row['Earnings Date'].tz_localize(None) if row['Earnings Date'].tz is not None else row['Earnings Date']
                    
                    # hist_1d의 index에서 가장 가까운 날짜를 찾음
                    hist_dates = hist_1d.index.tz_localize(None) if hist_1d.index.tz is not None else hist_1d.index
                    
                    try:
                        mask = hist_dates <= target_date + timedelta(days=1)
                        if mask.any():
                            idx_pos = mask.sum() - 1
                            if idx_pos > 0:
                                d_prev = float(hist_1d['Close'].iloc[idx_pos - 1])
                                d_curr = float(hist_1d['Close'].iloc[idx_pos])
                                d_pct = ((d_curr - d_prev) / d_prev) * 100
                                d_color = "#d32f2f" if d_pct < 0 else "#2e7d32"
                                d_sign = "+" if d_pct > 0 else ""
                                price_change_html = f"<span style='color:{d_color}; font-weight:bold;'>{d_sign}{d_pct:.1f}%</span><br><span style='font-size:0.85rem; color:#666;'>(${d_prev:.1f}➔${d_curr:.1f})</span>"
                    except:
                        pass
                        
                    edts_table += f"<tr><td><b>{row['Date']}</b></td><td>{est_str}</td><td><b>{rep_str}</b></td><td>{surprise_html}</td><td>{price_change_html}</td></tr>"
                edts_table += "</table>"
                earnings_html = edts_table
            else:
                earnings_html = "<p>최근 실적 데이터가 없습니다.</p>"
        except Exception as e:
            earnings_html = f"<p>실적 데이터를 불러올 수 없습니다. {e}</p>"

        news = ticker.news
        yh_news = "\n".join([f"- {n.get('title','')}" for n in news[:3]]) if news else ""
        inv_news = fetch_investing_news(ticker_symbol)
        raw_news = f"[Yahoo & Global News]\n{yh_news}\n\n[Google Deep News]\n{inv_news}"

        ma_html = f"""
        <table class="ma-table" style="font-size: 1.05rem;">
          <tr style='background-color: #f1f5f9;'><th>지표</th><th>상태/가격</th><th>발생일</th></tr>
          <tr><td><b>최근 크로스</b></td><td><b>{cross_type}</b></td><td>{cross_date}</td></tr>
          <tr><td><b>크로스 당시 주가</b></td><td>{cross_price}</td><td>-</td></tr>
          <tr><td><b>현재 4H MA200</b></td><td>{curr_4h_ma200}</td><td>-</td></tr>
          <tr><td><b>현재 1D MA200</b></td><td>{curr_1d_ma200}</td><td>-</td></tr>
        </table>
        """
        
        # 모멘텀 표에 거래량 데이터 병합
        mom_html = f"""
        <table class="ma-table" style="font-size: 1.05rem;">
          <tr style='background-color: #f1f5f9;'><th width="15%">기간</th><th>과거 ➔ 현재 주가 (변동률)</th></tr>
          <tr><td><b>1일</b></td><td>{vol_1d}</td></tr>
          <tr><td><b>1주일</b></td><td>{vol_1w}</td></tr>
          <tr><td><b>1개월</b></td><td>{vol_1m}</td></tr>
          <tr><td><b>1분기</b></td><td>{vol_1q}</td></tr>
          <tr><td><b>1년</b></td><td>{vol_1y}</td></tr>
        </table>
        <div style="margin-top: 10px; padding: 10px; background-color: #eef2ff; border-radius: 5px;">
            <b>📊 거래량 모멘텀:</b> 현재 {current_vol:,} 주 (20일 평균 {avg_vol_20d:,} 주 대비 
            <b>{round(current_vol/avg_vol_20d*100, 1) if avg_vol_20d else 0}%</b> 수준)
        </div>
        """

        return {
            "market_cap": mcap_str, "raw_news": raw_news, "ma_html": ma_html, 
            "momentum_html": mom_html, "earnings_html": earnings_html,
            "current_price": current_price, "current_vol": current_vol,
            "last_cross_type": cross_type, "last_cross_date": cross_date
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input="", saveticker_text=""):
    from api_utils import ask_gemini_dynamic
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    prompt = f"""
    당신은 월스트리트 기관 애널리스트입니다. 아래 데이터를 바탕으로 건조한(Dry) 문체로 리포트를 작성하세요.
    보고서 작성 기준일: {today_str}

    [분석 대상 데이터]
    - 종목명: {ticker} (섹터: {sector})
    - 시가총액: {fin_data.get('market_cap')}
    - 최신 뉴스(Yahoo & Investing): {fin_data.get('raw_news')}
    - SaveTicker 수집 뉴스: {saveticker_text}
    - 사용자 메모: {user_input}
    
    [작성 지침 - 반드시 아래 목차를 따를 것]
    1. 📊 시장 위치 및 밸류체인
       - 해당 종목의 섹터 내 위치와 연관된 밸류체인(공급망/경쟁사) 주식들의 동향을 요약.
    2. 📰 핵심 이슈 및 팩트체크 (날짜 매칭 필수)
       - 뉴스의 '정확한 발표 일자'와 '주가 변동 일자'를 매칭하여 팩트 기반으로 서술. 
       - "최근 급증했다" 같은 두리뭉실한 표현 절대 금지. "1일봉 차트 기준, O월 O일 파트너십 발표 직후 주가가 $O 수준으로 변동되었다"라고 명확히 서술할 것.
    3. 💡 트레이딩 결론 (Actionable Insight)
       - 1일봉(Daily) 관점에서 현재 포지션 진입에 대한 기계적이고 전문적인 조언.
       
    🚨 [경고]: 가격 변동률(%), 이평선 수치 등은 좌측에 표로 제공되므로 본문에 숫자를 중복 나열하지 마세요.
    """
    return ask_gemini_dynamic(prompt, [])
