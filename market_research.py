# ... existing code ...
        # 2. 기간별 변동성(수익률) 계산 로직
        hist = ticker.history(period="1y")
        if hist.empty: return {"error": "차트 데이터를 불러올 수 없는 종목입니다."}
            
        current_price = hist['Close'].iloc[-1]
        
        # --- 뉴 로직: 이평선 크로스 정밀 추적 및 테이블 생성 ---
        hist['MA50'] = hist['Close'].rolling(window=50).mean()
        hist['MA200'] = hist['Close'].rolling(window=200).mean()
        hist['Signal'] = (hist['MA50'] > hist['MA200']).astype(int)
        hist['Position'] = hist['Signal'].diff()

        cross_date, cross_price, cross_type = "최근 발생 안 함", "-", "-"
        crosses = hist[hist['Position'].isin([1.0, -1.0])]
        
        if not crosses.empty:
            last_cross = crosses.iloc[-1]
            cross_date = last_cross.name.strftime('%Y-%m-%d')
            cross_price = f"${last_cross['Close']:.2f}"
            cross_type = "🟢 골든크로스" if last_cross['Position'] == 1.0 else "🔴 데드크로스"

        cur_ma50 = hist['MA50'].iloc[-1] if not hist['MA50'].isna().all() else 0
        cur_ma200 = hist['MA200'].iloc[-1] if not hist['MA200'].isna().all() else 0
        
        # 마크다운 형태의 깔끔한 표(Table) 생성
        cross_table = f"| 지표 | 상태 및 가격 | 발생일 |\n|---|---|---|\n| **최근 크로스** | {cross_type} | {cross_date} |\n| **당시 주가** | {cross_price} | - |\n| **현재 50일선** | ${cur_ma50:.2f} | - |\n| **현재 200일선** | ${cur_ma200:.2f} | - |"
        # ----------------------------------------------------

        def calc_return(days_ago):
# ... existing code ...
        news_summary = "\n".join(news_headlines) if news_headlines else "최근 뉴스가 없습니다."

        return {
            "market_cap": mcap_str, "vol_1d": vol_1d, "vol_1w": vol_1w, "vol_1m": vol_1m,
            "vol_1q": vol_1q, "vol_1y": vol_1y, "raw_news": news_summary, "current_price": current_price,
            "cross_table": cross_table
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input=""):
    """수집된 금융 데이터와 유저의 입력을 바탕으로 AI 리포트를 작성합니다."""
    prompt = f"""
    당신은 팩트 기반의 객관적인 금융 데이터 분석가입니다. 아래는 [{ticker}] ({sector} 섹터) 종목 데이터입니다.
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
