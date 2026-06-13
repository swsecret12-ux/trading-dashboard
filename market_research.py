import yfinance as yf
import pandas as pd
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

        # 2. 기간별 차트 데이터 로드
        hist = ticker.history(period="1y")
        if hist.empty: return {"error": "차트 데이터를 불러올 수 없는 종목입니다. 티커명을 확인해주세요."}
            
        current_price = hist['Close'].iloc[-1]
        
        # 💡 50일선 vs 200일선 골든/데드크로스 정밀 추적 및 테이블 생성
        hist['MA50'] = hist['Close'].rolling(window=50).mean()
        hist['MA200'] = hist['Close'].rolling(window=200).mean()
        hist['Signal'] = (hist['MA50'] > hist['MA200']).astype(int)
        hist['Position'] = hist['Signal'].diff()

        cross_date, cross_price, cross_type = "최근 1년 내 발생 안 함", "-", "-"
        crosses = hist[hist['Position'].isin([1.0, -1.0])]
        
        if not crosses.empty:
            last_cross = crosses.iloc[-1]
            cross_date = last_cross.name.strftime('%Y-%m-%d')
            cross_price = f"${last_cross['Close']:.2f}"
            cross_type = "🟢 골든크로스" if last_cross['Position'] == 1.0 else "🔴 데드크로스"

        cur_ma50 = hist['MA50'].iloc[-1] if not pd.isna(hist['MA50'].iloc[-1]) else 0
        cur_ma200 = hist['MA200'].iloc[-1] if not pd.isna(hist['MA200'].iloc[-1]) else 0
        
        # 마크다운 형태의 깔끔한 표(Table) 생성
        cross_table = f"| 지표 | 상태 및 가격 | 발생일 |\n|---|---|---|\n| **최근 크로스** | {cross_type} | {cross_date} |\n| **당시 주가** | {cross_price} | - |\n| **현재 50일선** | ${cur_ma50:.2f} | - |\n| **현재 200일선** | ${cur_ma200:.2f} | - |"
        
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
            "current_price": current_price, "cross_table": cross_table
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input=""):
    """수집된 데이터와 현재 날짜를 바탕으로 세련된 AI 리포트를 작성합니다."""
    today_date = datetime.now().strftime('%Y년 %m월 %d일')
    
    prompt = f"""
    당신은 팩트 기반의 객관적인 금융 데이터 분석가입니다. 아래는 [{ticker}] ({sector} 섹터) 종목 데이터입니다.
    - 기준일자: {today_date}
    - 현재가: ${fin_data.get('current_price')}
    - 시가총액: {fin_data.get('market_cap')}
    - 변동성: 1일({fin_data.get('vol_1d')}%), 1주({fin_data.get('vol_1w')}%), 1달({fin_data.get('vol_1m')}%), 1년({fin_data.get('vol_1y')}%)
    - 최근 영문 뉴스: {fin_data.get('raw_news')}
    - 사용자 메모: {user_input}
    
    위 데이터를 바탕으로 화려한 미사여구나 과도한 이모지를 모두 배제하고, 건조하고 객관적인 핵심 수치 위주의 리서치 리포트를 한국어로 작성하세요.
    
    [필수 포함 항목]
    1. 가격 흐름 요약 (수치 기반)
    2. 주요 뉴스 팩트 체크
    3. 객관적 트레이딩 전망
    """
    return ask_gemini_dynamic(prompt, [])
