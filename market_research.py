import yfinance as yf
from api_utils import ask_gemini_dynamic

def fetch_financial_data(ticker_symbol):
    """야후 파이낸스를 통해 종목의 시총, 기간별 변동성, 최신 뉴스를 긁어옵니다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # 1. 시가총액 포맷팅 (야후 파이낸스 JSON 파싱 에러 완벽 방어)
        mcap_str = "데이터 없음"
        try:
            info = ticker.info
            market_cap = info.get('marketCap', 0)
            if market_cap > 1e12: mcap_str = f"{market_cap / 1e12:.2f}T (조 달러)"
            elif market_cap > 1e9: mcap_str = f"{market_cap / 1e9:.2f}B (십억 달러)"
            elif market_cap > 1e6: mcap_str = f"{market_cap / 1e6:.2f}M (백만 달러)"
        except:
            pass # 에러 발생 시 앱을 터뜨리지 않고 부드럽게 무시

        # 2. 기간별 변동성(수익률) 계산 로직
        hist = ticker.history(period="1y")
        if hist.empty: return {"error": "차트 데이터를 불러올 수 없는 종목입니다. 티커명을 확인해주세요."}
            
        current_price = hist['Close'].iloc[-1]
        
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

        # 3. 최신 뉴스 헤드라인 수집 (에러 방어)
        news_summary = "최근 뉴스가 없습니다."
        try:
            news_data = ticker.news
            news_headlines = []
            if news_data:
                for n in news_data[:5]: 
                    news_headlines.append(f"- {n.get('title', '')}")
            if news_headlines:
                news_summary = "\n".join(news_headlines)
        except:
            pass

        return {
            "market_cap": mcap_str, "vol_1d": vol_1d, "vol_1w": vol_1w, "vol_1m": vol_1m,
            "vol_1q": vol_1q, "vol_1y": vol_1y, "raw_news": news_summary, "current_price": current_price
        }
    except Exception as e:
        return {"error": f"데이터 수집 중 오류 발생: {str(e)}"}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input=""):
    """수집된 금융 데이터와 유저의 입력을 바탕으로 AI 리포트를 작성합니다."""
    prompt = f"""
    당신은 기관 애널리스트입니다. [{ticker}] ({sector} 섹터) 종목 데이터입니다.
    - 시가총액: {fin_data.get('market_cap')}
    - 변동성: 1일({fin_data.get('vol_1d')}%), 1주({fin_data.get('vol_1w')}%), 1달({fin_data.get('vol_1m')}%), 1년({fin_data.get('vol_1y')}%)
    - 최근 영문 뉴스: {fin_data.get('raw_news')}
    - 사용자 메모: {user_input}
    
    위 데이터를 종합하여 가격 모멘텀, 매크로 이슈 분석, 트레이딩 조언이 포함된 리서치 리포트를 한국어로 작성하세요.
    """
    return ask_gemini_dynamic(prompt, [])
