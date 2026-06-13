import yfinance as yf
import pandas as pd
import json
from api_utils import ask_gemini_dynamic

def fetch_financial_data(ticker_symbol):
    """야후 파이낸스를 통해 종목의 시총, 기간별 변동성, 최신 뉴스를 긁어옵니다."""
    try:
        # 코인인 경우 뒤에 -USD를 붙이거나, 주식인 경우 그대로 사용
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # 1. 시가총액 포맷팅
        market_cap = info.get('marketCap', 0)
        if market_cap > 1e12:
            mcap_str = f"{market_cap / 1e12:.2f}T (조 달러)"
        elif market_cap > 1e9:
            mcap_str = f"{market_cap / 1e9:.2f}B (십억 달러)"
        elif market_cap > 1e6:
            mcap_str = f"{market_cap / 1e6:.2f}M (백만 달러)"
        else:
            mcap_str = "데이터 없음"

        # 2. 기간별 변동성(수익률) 계산 로직
        hist = ticker.history(period="1y")
        if hist.empty:
            return {"error": "차트 데이터를 불러올 수 없는 종목입니다."}
            
        current_price = hist['Close'].iloc[-1]
        
        def calc_return(days_ago):
            if len(hist) > days_ago:
                past_price = hist['Close'].iloc[-(days_ago+1)]
                return round(((current_price - past_price) / past_price) * 100, 2)
            return 0.0

        vol_1d = calc_return(1)
        vol_1w = calc_return(5)   # 주식 시장 기준 1주일(5거래일)
        vol_1m = calc_return(20)  # 1개월(20거래일)
        vol_1q = calc_return(60)  # 1분기(60거래일)
        vol_1y = calc_return(250) # 1년(250거래일)

        # 3. 최신 뉴스 헤드라인 수집
        news_data = ticker.news
        news_headlines = []
        if news_data:
            for n in news_data[:5]: # 최근 5개 뉴스
                news_headlines.append(f"- {n.get('title', '')}")
        news_summary = "\n".join(news_headlines) if news_headlines else "최근 뉴스가 없습니다."

        return {
            "market_cap": mcap_str,
            "vol_1d": vol_1d, "vol_1w": vol_1w, "vol_1m": vol_1m,
            "vol_1q": vol_1q, "vol_1y": vol_1y,
            "raw_news": news_summary,
            "current_price": current_price
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input=""):
    """수집된 금융 데이터와 유저의 추가 입력을 바탕으로 AI 리서치 리포트를 작성합니다."""
    prompt = f"""
    당신은 월스트리트 최고 수준의 기관 애널리스트입니다.
    다음은 [{ticker}] ({sector} 섹터) 종목에 대해 방금 파이썬 봇이 수집한 실시간 금융 데이터입니다.

    [실시간 금융 데이터]
    - 시가총액: {fin_data.get('market_cap')}
    - 현재가 기준 수익률(변동성): 1일({fin_data.get('vol_1d')}%), 1주({fin_data.get('vol_1w')}%), 1달({fin_data.get('vol_1m')}%), 1분기({fin_data.get('vol_1q')}%), 1년({fin_data.get('vol_1y')}%)
    - 최근 영문 뉴스 헤드라인:
    {fin_data.get('raw_news')}

    [사용자 추가 지표/메모]
    {user_input}

    위 데이터를 종합하여 이 종목과 섹터에 대한 **'심층 투자 리서치 리포트'**를 한국어로 작성해 주세요.
    
    필수 포함 내용:
    1. 가격 모멘텀 분석 (1일~1년 수익률을 바탕으로 현재 주가 흐름 진단)
    2. 매크로 및 이슈 분석 (제공된 영문 뉴스를 해석하여 현재 이 종목을 움직이는 핵심 호재/악재 파악)
    3. 종합 트레이딩 조언 (펀더멘털과 모멘텀을 고려한 향후 전망)
    
    가독성 좋게 이모지와 글머리 기호를 적절히 사용하여 보고서 형태로 깔끔하게 출력해 주세요.
    """
    
    return ask_gemini_dynamic(prompt, [])
