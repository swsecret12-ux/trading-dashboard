import yfinance as yf
from datetime import datetime
from api_utils import ask_gemini_dynamic

def fetch_financial_data(ticker_symbol):
    """야후 파이낸스를 통해 종목의 현재가, 시총, 변동성, 이평선, 뉴스를 긁어옵니다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # 1. 시가총액 포맷팅
        market_cap = info.get('marketCap', 0)
        if market_cap > 1e12: mcap_str = f"{market_cap / 1e12:.2f}T (조 달러)"
        elif market_cap > 1e9: mcap_str = f"{market_cap / 1e9:.2f}B (십억 달러)"
        elif market_cap > 1e6: mcap_str = f"{market_cap / 1e6:.2f}M (백만 달러)"
        else: mcap_str = "데이터 없음"

        # 2. 기간별 차트 데이터 로드 및 이평선(MA) 계산
        hist = ticker.history(period="1y")
        if hist.empty: return {"error": "차트 데이터를 불러올 수 없는 종목입니다. 티커명을 확인해주세요."}
            
        current_price = hist['Close'].iloc[-1]
        
        # 💡 50일선 vs 200일선 골든/데드크로스 판독
        ma_50 = hist['Close'].tail(50).mean() if len(hist) >= 50 else current_price
        ma_200 = hist['Close'].tail(200).mean() if len(hist) >= 200 else current_price
        
        if ma_50 > ma_200:
            cross_status = f"🟢 골든크로스 상승장 (50일선이 200일선 위 위치)"
        else:
            cross_status = f"🔴 데드크로스 하락장 (50일선이 200일선 아래 위치)"
        
        # 3. 변동성(수익률) 계산 로직
        def calc_return(days_ago):
            if len(hist) > days_ago:
                past_price = hist['Close'].iloc[-(days_ago+1)]
                return round(((current_price - past_price) / past_price) * 100, 2)
            return 0.0

        vol_1d = calc_return(1)
        vol_1w = calc_return(5)   
        vol_1m = calc_return(20)  
        vol_1q = calc_return(60)  
        vol_1y = calc_return(250) 

        # 4. 최신 뉴스 헤드라인 수집 (빈칸 오류 방어)
        news_data = ticker.news
        news_headlines = []
        if news_data:
            for n in news_data[:5]: 
                # API 구조 변동에 대비하여 title 위치를 다중으로 찾습니다.
                title = n.get('title', '')
                if not title: title = n.get('content', {}).get('title', '')
                if title: news_headlines.append(f"- {title}")
                
        news_summary = "\n".join(news_headlines) if news_headlines else "최근 관련 뉴스를 불러오지 못했습니다."

        return {
            "market_cap": mcap_str, "vol_1d": vol_1d, "vol_1w": vol_1w, "vol_1m": vol_1m,
            "vol_1q": vol_1q, "vol_1y": vol_1y, "raw_news": news_summary, 
            "current_price": current_price, "ma_status": cross_status
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input=""):
    """수집된 데이터와 현재 날짜를 바탕으로 세련된 AI 리포트를 작성합니다."""
    today_date = datetime.now().strftime('%Y년 %m월 %d일')
    
    prompt = f"""
    당신은 월스트리트의 탑티어 기관 애널리스트입니다. 
    반드시 기준일자({today_date})를 명시하여, 아래 [{ticker}] ({sector} 섹터) 종목 데이터를 바탕으로 심층 리서치 리포트를 작성하세요.

    [실시간 금융 데이터]
    - 현재 가격: ${fin_data.get('current_price')}
    - 이평선 추세: {fin_data.get('ma_status')}
    - 시가총액: {fin_data.get('market_cap')}
    - 변동성(수익률): 1일({fin_data.get('vol_1d')}%), 1주({fin_data.get('vol_1w')}%), 1달({fin_data.get('vol_1m')}%), 1년({fin_data.get('vol_1y')}%)
    - 최근 영문 뉴스: {fin_data.get('raw_news')}
    - 사용자 핵심 메모: {user_input}
    
    [작성 가이드라인]
    1. 도입부에 반드시 "📅 작성일: {today_date}"를 가장 먼저 적어주세요.
    2. '현재가 및 이평선 추세(골든/데드크로스)'를 바탕으로 한 가격 모멘텀을 심층 분석하세요.
    3. 최신 뉴스(호재/악재)를 반영한 펀더멘털 전망을 세련되고 날카로운 문체로 요약하세요.
    4. 너무 밋밋하지 않게 이모지(📊, 💡, 🚨 등)와 굵은 글씨(**)를 적극 활용하여 예쁜 보고서 형태로 꾸며주세요.
    """
    return ask_gemini_dynamic(prompt, [])
