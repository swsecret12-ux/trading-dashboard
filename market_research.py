import yfinance as yf
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from api_utils import ask_gemini_dynamic

def fetch_financial_data(ticker_symbol):
    """야후 파이낸스를 통해 종목의 가격, 기간별 변동성, 4H/1D 이평선, 실적, 최신 뉴스를 긁어옵니다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # 1. 시가총액 포맷팅
        market_cap = info.get('marketCap', 0)
        if market_cap > 1e12: mcap_str = f"{market_cap / 1e12:.2f}T (조 달러)"
        elif market_cap > 1e9: mcap_str = f"{market_cap / 1e9:.2f}B (십억 달러)"
        elif market_cap > 1e6: mcap_str = f"{market_cap / 1e6:.2f}M (백만 달러)"
        else: mcap_str = "데이터 없음"

        hist_1d = ticker.history(period="2y", interval="1d")
        hist_1h = ticker.history(period="730d", interval="1h")
        
        if hist_1d.empty: return {"error": "차트 데이터를 불러올 수 없는 종목입니다."}
        
        current_price = float(hist_1d['Close'].iloc[-1])
        current_vol = int(hist_1d['Volume'].iloc[-1])
        avg_vol_10d = int(hist_1d['Volume'].tail(10).mean())
        
        def calc_return(days_ago, label):
            if len(hist_1d) > days_ago:
                past_price = float(hist_1d['Close'].iloc[-(days_ago+1)])
                pct = round(((current_price - past_price) / past_price) * 100, 2)
                
                # 한국식 주식 컬러: 상승(빨강), 하락(파랑)
                color = "red" if pct > 0 else ("blue" if pct < 0 else "black")
                sign = "+" if pct > 0 else ""
                return f"<tr><td>{label}</td><td>${past_price:.2f}</td><td>${current_price:.2f}</td><td><span style='color:{color}; font-weight:bold;'>{sign}{pct}%</span></td></tr>"
            return ""

        momentum_rows = calc_return(1, "1일 (1D)")
        momentum_rows += calc_return(5, "1주 (1W)")
        momentum_rows += calc_return(20, "1개월 (1M)")
        momentum_rows += calc_return(60, "1분기 (1Q)")
        momentum_rows += calc_return(250, "1년 (1Y)")
        
        vol_color = "red" if current_vol > avg_vol_10d else "blue"
        
        momentum_html = f"""
        <table class="ma-table">
          <tr><th>기간</th><th>과거 가격</th><th>현재 가격</th><th>변동률</th></tr>
          {momentum_rows}
          <tr><td colspan="4" style="text-align:right; font-size:0.9em; color:#555;">
          <b>현재 거래량:</b> <span style='color:{vol_color};'>{current_vol:,}</span> (10일 평균: {avg_vol_10d:,})
          </td></tr>
        </table>
        """

        ma_html = ""
        last_cross_type = "-"
        
        if not hist_1h.empty:
            # 타임존 제거 (비교를 위해)
            hist_1d.index = hist_1d.index.tz_localize(None)
            hist_1h.index = hist_1h.index.tz_localize(None)
            
            # 1D 200MA 계산
            hist_1d['MA200_1D'] = hist_1d['Close'].rolling(window=200).mean()
            
            # 1H 데이터를 4H로 리샘플링 후 4H 200MA 계산
            hist_4h = hist_1h['Close'].resample('4H').last().dropna().to_frame()
            hist_4h['MA200_4H'] = hist_4h['Close'].rolling(window=200).mean()
            
            # 날짜 기준으로 병합
            hist_1d['date'] = hist_1d.index.date
            hist_4h['date'] = hist_4h.index.date
            
            ma1d_dict = dict(zip(hist_1d['date'], hist_1d['MA200_1D']))
            hist_4h['MA200_1D'] = hist_4h['date'].map(ma1d_dict).ffill()
            
            # 결측치 제거 후 크로스 포인트 찾기
            merged = hist_4h.dropna(subset=['MA200_4H', 'MA200_1D']).copy()
            merged['Prev_MA200_4H'] = merged['MA200_4H'].shift(1)
            merged['Prev_MA200_1D'] = merged['MA200_1D'].shift(1)
            
            golden = merged[(merged['MA200_4H'] > merged['MA200_1D']) & (merged['Prev_MA200_4H'] <= merged['Prev_MA200_1D'])]
            dead = merged[(merged['MA200_4H'] < merged['MA200_1D']) & (merged['Prev_MA200_4H'] >= merged['Prev_MA200_1D'])]
            
            last_cross_date = "-"
            last_cross_price = "-"
            
            if not golden.empty or not dead.empty:
                g_idx = golden.index[-1] if not golden.empty else None
                d_idx = dead.index[-1] if not dead.empty else None
                
                if g_idx and d_idx: latest_idx = max(g_idx, d_idx)
                else: latest_idx = g_idx if g_idx else d_idx
                    
                last_cross_type = "<span style='color:red; font-weight:bold;'>🟢 골든크로스 상승장</span>" if latest_idx == g_idx else "<span style='color:blue; font-weight:bold;'>🔴 데드크로스 하락장</span>"
                last_cross_date = latest_idx.strftime('%Y-%m-%d %H:%M')
                last_cross_price = f"${merged.loc[latest_idx, 'Close']:.2f}"
            
            curr_4h_200 = merged['MA200_4H'].iloc[-1] if not merged.empty else 0
            curr_1d_200 = merged['MA200_1D'].iloc[-1] if not merged.empty else 0
            
            ma_html = f"""
            <table class="ma-table">
              <tr><th>지표</th><th>상태 및 가격</th><th>발생 일시</th></tr>
              <tr><td><b>최근 크로스 추세</b></td><td>{last_cross_type}</td><td>{last_cross_date}</td></tr>
              <tr><td><b>당시 주가</b></td><td>{last_cross_price}</td><td>-</td></tr>
              <tr><td><b>현재 4시간봉 200선</b></td><td>${curr_4h_200:.2f}</td><td>-</td></tr>
              <tr><td><b>현재 1일봉 200선</b></td><td>${curr_1d_200:.2f}</td><td>-</td></tr>
            </table>
            """
        else:
            ma_html = "<p>4시간봉 데이터를 제공하지 않는 종목입니다.</p>"

        earnings_html = ""
        try:
            earns = ticker.get_earnings_dates(limit=10)
            if earns is not None and not earns.empty:
                earns = earns.reset_index()
                now_utc = pd.Timestamp.utcnow()
                if earns['Earnings Date'].dt.tz is None: earns['Earnings Date'] = earns['Earnings Date'].dt.tz_localize('UTC')
                
                future = earns[earns['Earnings Date'] > now_utc]
                past = earns[earns['Earnings Date'] <= now_utc].head(4)
                
                next_date = future.iloc[-1]['Earnings Date'].strftime('%Y-%m-%d') if not future.empty else "미정"
                
                earnings_rows = ""
                for _, r in past.iterrows():
                    d_str = r['Earnings Date'].strftime('%Y-%m-%d')
                    est = f"{r['EPS Estimate']:.2f}" if pd.notna(r['EPS Estimate']) else "-"
                    act = f"{r['Reported EPS']:.2f}" if pd.notna(r['Reported EPS']) else "-"
                    
                    # 어닝 서프라이즈(빨강), 쇼크(파랑) 컬러링
                    if pd.notna(r['Reported EPS']) and pd.notna(r['EPS Estimate']):
                        color = "red" if r['Reported EPS'] > r['EPS Estimate'] else ("blue" if r['Reported EPS'] < r['EPS Estimate'] else "black")
                    else: color = "black"
                    
                    earnings_rows += f"<tr><td>{d_str}</td><td>{est}</td><td style='color:{color}; font-weight:bold;'>{act}</td></tr>"
                    
                earnings_html = f"""
                <p style='margin-bottom:5px;'><b>📅 다음 실적발표일:</b> <span style='color:#1e40af;'>{next_date}</span></p>
                <table class="ma-table">
                  <tr><th>발표일 (과거 4분기)</th><th>예상 EPS</th><th>실제 EPS</th></tr>
                  {earnings_rows}
                </table>
                """
        except Exception as e:
            earnings_html = "<p>실적 데이터를 불러올 수 없습니다.</p>"

        news_data = ticker.news
        news_headlines = [f"- [Yahoo] {n.get('title', '')}" for n in news_data[:3]] if news_data else []
        
        try:
            # 구글 뉴스 RSS를 우회하여 인베스팅닷컴 기사 제목 긁어오기
            url = f"https://news.google.com/rss/search?q=site:investing.com+{ticker_symbol}+news&hl=en-US&gl=US&ceid=US:en"
            res = requests.get(url, timeout=5)
            soup = BeautifulSoup(res.content, features='xml')
            items = soup.findAll('item')
            if items:
                news_headlines += [f"- [Investing.com] {item.title.text}" for item in items[:3]]
        except: pass
        
        news_summary = "\n".join(news_headlines) if news_headlines else "최근 뉴스가 없습니다."

        return {
            "market_cap": mcap_str, "current_price": current_price, "cross_type": last_cross_type,
            "raw_news": news_summary, "ma_html": ma_html, "momentum_html": momentum_html, "earnings_html": earnings_html
        }
    except Exception as e:
        return {"error": str(e)}

def fetch_saveticker_news(user_id, password):
    if not user_id or not password: return "SaveTicker 계정이 없어 수집을 생략했습니다."
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        session.post("https://www.saveticker.com/api/auth/callback/credentials", data={"email": user_id, "password": password}, timeout=10)
        news_res = session.get("https://www.saveticker.com/news", timeout=10)
        soup = BeautifulSoup(news_res.text, 'html.parser')
        paragraphs = soup.find_all(['p', 'h1', 'h2', 'h3', 'article'])
        news_text = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
        return f"[SaveTicker 자동 수집 뉴스 요약]\n{news_text[:2500]}" if news_text else "사이트 접속 성공했으나 뉴스 본문을 찾지 못했습니다."
    except Exception as e:
        return f"SaveTicker 자동 수집 중 오류: {str(e)}"

def analyze_sector_with_ai(ticker, sector, fin_data, user_input="", saveticker_text=""):
    today_str = datetime.today().strftime('%Y-%m-%d')
    prompt = f"""
    당신은 월스트리트의 최정상급 기관 애널리스트입니다. 미사여구와 감정적인 표현은 완전히 빼고, **오직 팩트와 데이터 위주의 건조한(Dry) 문체**로 리포트를 작성하세요.
    보고서 작성 기준일: {today_str}

    [분석 대상 데이터]
    - 종목명: {ticker} (소속 섹터: {sector})
    - 시가총액: {fin_data.get('market_cap')}
    - 현재가: ${fin_data.get('current_price', 0):.2f}
    - 4H/1D 200이평 크로스 추세: {fin_data.get('cross_type')}
    - 수집된 해외 뉴스(Yahoo, Investing.com): {fin_data.get('raw_news')}
    - 사용자 메모 및 자동 수집된 외부 팩트(SaveTicker 등): {user_input} \n {saveticker_text}
    
    [작성 지침 - 반드시 아래 목차를 따를 것]
    1. 📊 시장 위치 및 경쟁 밸류체인 분석
       - 해당 주식이 글로벌 {sector} 섹터 내에서 시가총액 기준으로 어느 정도 위치(몇 위권 수준 등)인지 명확히 짚어주세요.
       - 연계된 주요 경쟁사(Peers) 또는 공급망(Supply Chain) 주식들의 최근 동향을 교차 분석하세요.
    2. 📰 핵심 이슈 및 팩트체크 (뉴스 기반)
       - 제공된 뉴스(Yahoo, Investing, SaveTicker 등)를 크로스체크하여, 현재 주가 상승/하락의 트리거가 된 진짜 팩트만 서술하세요.
       - 루머성 찌라시와 팩트를 분리하여 평가하세요.
    3. 💡 기관 트레이딩 결론 (Actionable Insight)
       - 시총 위치, 뉴스 모멘텀, 이평선 크로스 추세를 종합하여 현재 포지션 진입(Long/Short/관망)에 대한 건조하고 기계적인 셋업 조언을 제공하세요.
    """
    return ask_gemini_dynamic(prompt, [])
