import yfinance as yf
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from api_utils import ask_gemini_dynamic

def fetch_financial_data(ticker_symbol):
    """야후 파이낸스를 통해 종목의 가격, 기간별 변동성, 이평선, 최신 뉴스를 긁어옵니다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # 1. 시가총액 포맷팅
        market_cap = info.get('marketCap', 0)
        if market_cap > 1e12: mcap_str = f"{market_cap / 1e12:.2f}T (조 달러)"
        elif market_cap > 1e9: mcap_str = f"{market_cap / 1e9:.2f}B (십억 달러)"
        elif market_cap > 1e6: mcap_str = f"{market_cap / 1e6:.2f}M (백만 달러)"
        else: mcap_str = "데이터 없음"

        # 2. 기간별 변동성(수익률) 및 과거 가격 계산
        hist = ticker.history(period="2y") # 이평선 계산을 위해 2년치 로드
        if hist.empty: return {"error": "차트 데이터를 불러올 수 없는 종목입니다."}
            
        current_price = float(hist['Close'].iloc[-1])
        current_vol = int(hist['Volume'].iloc[-1])
        
        def calc_return(days_ago):
            if len(hist) > days_ago:
                past_price = float(hist['Close'].iloc[-(days_ago+1)])
                pct = round(((current_price - past_price) / past_price) * 100, 2)
                sign = "+" if pct > 0 else ""
                return f"${past_price:.2f} ➔ ${current_price:.2f} ({sign}{pct}%)"
            return "데이터 부족"

        vol_1d = calc_return(1)
        vol_1w = calc_return(5)   
        vol_1m = calc_return(20)  
        vol_1q = calc_return(60)  
        vol_1y = calc_return(250) 

        # 3. MA50, MA200 및 크로스 계산 로직
        hist['MA50'] = hist['Close'].rolling(window=50).mean()
        hist['MA200'] = hist['Close'].rolling(window=200).mean()
        
        current_ma50 = float(hist['MA50'].iloc[-1])
        current_ma200 = float(hist['MA200'].iloc[-1])
        
        # 최근 크로스 지점 찾기 (1년 이내)
        hist_1y = hist.tail(250).copy()
        hist_1y['Prev_MA50'] = hist_1y['MA50'].shift(1)
        hist_1y['Prev_MA200'] = hist_1y['MA200'].shift(1)
        
        golden_crosses = hist_1y[(hist_1y['MA50'] > hist_1y['MA200']) & (hist_1y['Prev_MA50'] <= hist_1y['Prev_MA200'])]
        dead_crosses = hist_1y[(hist_1y['MA50'] < hist_1y['MA200']) & (hist_1y['Prev_MA50'] >= hist_1y['Prev_MA200'])]
        
        last_cross_type = "-"
        last_cross_date = "-"
        last_cross_price = "-"
        
        if not golden_crosses.empty or not dead_crosses.empty:
            g_idx = golden_crosses.index[-1] if not golden_crosses.empty else None
            d_idx = dead_crosses.index[-1] if not dead_crosses.empty else None
            
            if g_idx and d_idx:
                latest_idx = max(g_idx, d_idx)
            else:
                latest_idx = g_idx if g_idx else d_idx
                
            last_cross_type = "🟢 골든크로스" if latest_idx == g_idx else "🔴 데드크로스"
            last_cross_date = latest_idx.strftime('%Y-%m-%d')
            last_cross_price = f"${hist_1y.loc[latest_idx, 'Close']:.2f}"

        # 4. 최신 뉴스 헤드라인 수집
        news_data = ticker.news
        news_headlines = []
        if news_data:
            for n in news_data[:5]: 
                news_headlines.append(f"- {n.get('title', '')}")
        news_summary = "\n".join(news_headlines) if news_headlines else "최근 뉴스가 없습니다."

        return {
            "market_cap": mcap_str, "vol_1d": vol_1d, "vol_1w": vol_1w, "vol_1m": vol_1m,
            "vol_1q": vol_1q, "vol_1y": vol_1y, "raw_news": news_summary, "current_price": current_price,
            "current_vol": current_vol, "ma50": current_ma50, "ma200": current_ma200,
            "last_cross_type": last_cross_type, "last_cross_date": last_cross_date, "last_cross_price": last_cross_price
        }
    except Exception as e:
        return {"error": str(e)}

def fetch_saveticker_news(user_id, password):
    """파이썬 봇이 브라우저로 위장하여 SaveTicker 로그인을 시도하고 뉴스를 긁어옵니다."""
    if not user_id or not password:
        return "SaveTicker 계정 정보가 입력되지 않아 수집을 생략했습니다."

    try:
        # 가상의 세션을 열고 일반 크롬 브라우저인 척 위장(User-Agent)합니다.
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        session.headers.update(headers)

        # 1. 로그인 시도
        login_url = "https://www.saveticker.com/api/auth/callback/credentials"
        payload = {
            "email": user_id, 
            "password": password
        }
        session.post(login_url, data=payload, timeout=10)

        # 2. 뉴스 페이지 접근
        news_url = "https://www.saveticker.com/news"
        news_res = session.get(news_url, timeout=10)

        # 3. 뷰티풀수프(BeautifulSoup)를 이용해 HTML에서 기사 본문 텍스트만 추출
        soup = BeautifulSoup(news_res.text, 'html.parser')
        paragraphs = soup.find_all(['p', 'h1', 'h2', 'h3', 'article'])
        news_text = "\n".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])

        if not news_text:
            return "[SaveTicker 크롤링 결과] 사이트 접속은 성공했으나 뉴스 본문을 찾지 못했습니다. (봇 차단 또는 사이트 구조 다름)"

        # AI 분석을 위해 텍스트가 너무 길면 잘라냅니다.
        return f"[SaveTicker 자동 수집 뉴스 요약]\n{news_text[:2500]}"

    except Exception as e:
        return f"[SaveTicker 크롤링 에러] 자동 수집 중 오류가 발생했습니다: {str(e)}"

def analyze_sector_with_ai(ticker, sector, fin_data, user_input="", saveticker_text=""):
    """수집된 금융 데이터와 크롤링한 뉴스를 바탕으로 팩트 위주의 건조한 AI 리포트를 작성합니다."""
    today_str = datetime.today().strftime('%Y-%m-%d')
    
    # 딕셔너리 안전 접근 (에러 원천 차단)
    current_price = fin_data.get('current_price', 0.0)
    current_vol = fin_data.get('current_vol', 0)
    ma50 = fin_data.get('ma50', 0.0)
    ma200 = fin_data.get('ma200', 0.0)
    
    prompt = f"""
    당신은 월스트리트의 최정상급 기관 애널리스트입니다. 미사여구와 감정적인 표현은 철저히 배제하고, 오직 데이터와 팩트 기반의 건조한(Dry) 문체로 리포트를 작성하세요.
    보고서 작성 기준일: {today_str}

    [분석 대상 데이터]
    - 종목명: {ticker} (소속 섹터: {sector})
    - 시가총액: {fin_data.get('market_cap')}
    - 현재가/거래량: ${current_price:.2f} / {current_vol}
    - 가격 변동: 1일({fin_data.get('vol_1d')}), 1주({fin_data.get('vol_1w')}), 1달({fin_data.get('vol_1m')}), 1년({fin_data.get('vol_1y')})
    - 이평선 현황: MA50(${ma50:.2f}) / MA200(${ma200:.2f})
    - 최근 크로스: {fin_data.get('last_cross_type')} (발생일: {fin_data.get('last_cross_date')}, 당시가격: {fin_data.get('last_cross_price')})
    - 야후 파이낸스 최신 뉴스: {fin_data.get('raw_news')}
    
    [사용자 메모 및 자동 수집된 외부 팩트(SaveTicker 등)]
    사용자 메모: {user_input}
    외부 수집 뉴스: {saveticker_text}
    
    [작성 지침 - 반드시 아래 목차를 따를 것]
    1. 📊 시장 위치 및 경쟁 시황
       - 이 종목이 글로벌 {sector} 섹터 내에서 시가총액 기준으로 어느 정도 위치에 있는지 평가.
       - 주요 경쟁사(Peers) 또는 강력하게 연계된 공급망 주식들의 동향 간략 요약.
    2. 📈 가격 및 거래량 모멘텀 분석
       - 기간별 과거 가격 대비 현재가 변동률과 거래량을 바탕으로 모멘텀 팩트 분석.
       - MA50과 MA200을 비교하여 현재 단기/장기 추세 진단.
    3. 📰 핵심 이슈 및 팩트체크 (뉴스 기반)
       - 제공된 야후 뉴스 및 외부 수집 뉴스를 크로스체크하여 상승/하락의 트리거가 된 팩트만 서술.
    4. 💡 트레이딩 결론 (Actionable Insight)
       - 펀더멘털과 모멘텀을 종합하여 현재 포지션 진입(Long/Short/관망)에 대한 기계적인 조언.
    """
    return ask_gemini_dynamic(prompt, [])
