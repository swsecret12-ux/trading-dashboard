import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timezone
from api_utils import ask_gemini_dynamic

def get_robust_session():
    """야후 파이낸스 접속 차단을 우회하기 위한 강력한 세션 헤더 설정"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })
    return session

def get_earnings_html_via_api(ticker):
    """lxml 에러를 완벽하게 피하기 위해 야후 내부 JSON API에서 실적 데이터를 직접 파싱합니다."""
    try:
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=earningsHistory,calendarEvents"
        session = get_robust_session()
        res = session.get(url, timeout=5)
        data = res.json()
        
        rows = []
        
        # 1. 미래 실적 (예정일)
        calendar = data.get('quoteSummary', {}).get('result', [{}])[0].get('calendarEvents', {}).get('earnings', {})
        earnings_dates = calendar.get('earningsDate', [])
        if earnings_dates:
            future_date = ""
            if isinstance(earnings_dates[0], dict):
                future_date = earnings_dates[0].get('fmt', '')
            elif isinstance(earnings_dates[0], int):
                future_date = datetime.fromtimestamp(earnings_dates[0], timezone.utc).strftime('%Y-%m-%d')
                
            if future_date:
                est = calendar.get('earningsAverage', {}).get('raw', '')
                rows.append(f"<tr style='background-color:#fffbea;'><td>⏳ {future_date} (예정)</td><td>{est if est else '-'}</td><td>-</td><td>-</td><td>-</td></tr>")
        
        # 2. 과거 실적 히스토리
        history = data.get('quoteSummary', {}).get('result', [{}])[0].get('earningsHistory', {}).get('history', [])
        for item in reversed(history): # 최근 발표가 위로 오도록 뒤집기
            date_str = item.get('quarter', {}).get('fmt', '')
            if not date_str: continue
            
            eps_est = item.get('epsEstimate', {}).get('fmt', '-')
            eps_act = item.get('epsActual', {}).get('fmt', '-')
            surp = item.get('surprisePercent', {}).get('raw', '-')
            
            surp_html = "-"
            if isinstance(surp, (int, float)):
                color = "#22c55e" if surp > 0 else "#ef4444"
                surp_html = f"<span style='color:{color}; font-weight:bold;'>{surp*100:.1f}% {'상회' if surp > 0 else '하회'}</span>"
            
            rows.append(f"<tr><td>{date_str}</td><td>{eps_est}</td><td>{eps_act}</td><td>{surp_html}</td><td>-</td></tr>")
            
        if not rows:
            return "<p>최근 실적 데이터를 불러올 수 없습니다.</p>"
            
        # 테이블 HTML 조립
        html = "<table class='ma-table'><tr><th>발표일(분기)</th><th>시장 예상치</th><th>실제 발표치</th><th>서프라이즈</th><th>발표일 주가 등락</th></tr>"
        html += "".join(rows)
        html += "</table>"
        return html
    except Exception as e:
        return f"<p style='color:#ef4444;'>최근 실적 데이터를 불러올 수 없습니다.</p>"

def fetch_financial_data(ticker_symbol):
    """야후 파이낸스 데이터를 크롤링하고 지표를 계산합니다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        market_cap = info.get('marketCap', 0)
        
        df_1d = ticker.history(period="1y", interval="1d")
        df_1h = ticker.history(period="730d", interval="1h")
        ndx = yf.Ticker("^IXIC").history(period="1y", interval="1d")
        
        if df_1d.empty or df_1h.empty:
            return {"error": "차트 데이터를 가져올 수 없습니다."}
            
        current_price = df_1d['Close'].iloc[-1]
        
        # 4H vs 1D EMA 200 크로스 계산
        df_1d_ma = pd.DataFrame({'Close': df_1d['Close']})
        df_1d_ma['EMA200_1D'] = df_1d_ma['Close'].ewm(span=200, adjust=False).mean()
        
        df_4h_ma = df_1h.resample('4h').agg({'Close': 'last'}).dropna()
        df_4h_ma['EMA200_4H'] = df_4h_ma['Close'].ewm(span=200, adjust=False).mean()
        
        df_1d_ma.index = pd.to_datetime(df_1d_ma.index, utc=True)
        df_4h_ma.index = pd.to_datetime(df_4h_ma.index, utc=True)
        
        df_1d_ma = df_1d_ma[['EMA200_1D']].sort_index()
        df_4h_ma = df_4h_ma[['EMA200_4H', 'Close']].sort_index()
        
        merged = pd.merge_asof(df_4h_ma, df_1d_ma, left_index=True, right_index=True, direction='backward').dropna()
        merged['Prev_4H'] = merged['EMA200_4H'].shift(1)
        merged['Prev_1D'] = merged['EMA200_1D'].shift(1)
        
        gc = merged[(merged['EMA200_4H'] > merged['EMA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
        dc = merged[(merged['EMA200_4H'] < merged['EMA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])]
        
        last_cross_type = "최근 1년 내 크로스 없음"
        last_cross_date = "-"
        ma_html = "<p>최근 1년 내 4H/1D EMA 200 크로스가 없습니다.</p>"
        
        if not gc.empty or not dc.empty:
            last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize('UTC')
            last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize('UTC')
            latest_idx = max(last_gc, last_dc)
            
            cross_name = "🟢 골든크로스" if latest_idx == last_gc else "🔴 데드크로스"
            days_diff = (datetime.now(timezone.utc) - latest_idx).days
            if days_diff <= 90: cross_name = f"🔥 {cross_name}"
                
            last_cross_type = cross_name
            last_cross_date = latest_idx.strftime('%Y-%m-%d %H:%M')
            
            color = "#22c55e" if "골든" in cross_name else "#ef4444"
            ma_html = f"<ul><li><b>상태:</b> <span style='color:{color}; font-weight:bold;'>{cross_name}</span></li>"
            ma_html += f"<li><b>발생일:</b> {last_cross_date}</li>"
            ma_html += f"<li><b>당시 주가:</b> ${merged.loc[latest_idx, 'Close']:.2f}</li></ul>"
            
        ret_1m = ((current_price - df_1d['Close'].iloc[-21]) / df_1d['Close'].iloc[-21]) * 100 if len(df_1d) > 21 else 0
        ret_3m = ((current_price - df_1d['Close'].iloc[-63]) / df_1d['Close'].iloc[-63]) * 100 if len(df_1d) > 63 else 0
        
        momentum_html = f"<ul><li><b>현재가:</b> ${current_price:.2f}</li>"
        momentum_html += f"<li><b>1개월 변동:</b> {ret_1m:+.2f}%</li>"
        momentum_html += f"<li><b>3개월 변동:</b> {ret_3m:+.2f}%</li></ul>"

        df_1d.index = df_1d.index.normalize()
        ndx.index = ndx.index.normalize()
        
        df_1d['Daily_Return'] = df_1d['Close'].pct_change() * 100
        ndx['Daily_Return'] = ndx['Close'].pct_change() * 100
        
        last_90_days = df_1d.last('90D')
        big_moves_df = last_90_days[abs(last_90_days['Daily_Return']) >= 10.0]
        
        move_records = []
        for date, row in big_moves_df.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            move_pct = row['Daily_Return']
            try:
                ndx_move = ndx.loc[date]['Daily_Return']
                if isinstance(ndx_move, pd.Series): ndx_move = ndx_move.iloc[0]
            except Exception:
                ndx_move = 0.0
                
            move_records.append({
                "date": date_str,
                "ticker_move": f"{move_pct:+.1f}%",
                "ndx_move": f"{ndx_move:+.1f}%"
            })
        
        earnings_html = get_earnings_html_via_api(ticker_symbol)
        
        news_items = ticker.news
        news_lines = []
        if news_items:
            for n in news_items[:10]:
                title = n.get('title', '')
                if not title: title = n.get('content', {}).get('title', '')
                pub_time = n.get('providerPublishTime', 0)
                date_str = pd.to_datetime(pub_time, unit='s').strftime('%Y-%m-%d') if pub_time else "날짜미상"
                if title: news_lines.append(f"- [{date_str}] {title}")
        raw_news = "\n".join(news_lines) if news_lines else "최근 뉴스가 없습니다."

        return {
            "market_cap": market_cap,
            "last_cross_type": last_cross_type,
            "last_cross_date": last_cross_date,
            "ma_html": ma_html,
            "momentum_html": momentum_html,
            "earnings_html": earnings_html,
            "raw_news": raw_news,
            "big_moves": move_records
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_issue, news_content):
    """AI에게 과거 핵심 팩트(파트너십 등)를 무조건 찾아내도록 강제하는 분석 로직"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    moves_text = ""
    moves = fin_data.get("big_moves", [])
    if moves:
        for m in moves:
            moves_text += f"- 발생일: {m['date']}, 종목 등락률: {m['ticker_move']}, 나스닥 등락률: {m['ndx_move']}\n"
    else:
        moves_text = "최근 3개월 내 10% 이상 급변동 없음."

    prompt = f"""
    당신은 월스트리트 수석 애널리스트입니다. 아래 데이터를 바탕으로 완벽한 투자 분석 보고서를 마크다운으로 작성하세요.
    
    [분석 대상]
    - 종목: {ticker} (섹터: {sector})
    - 기준일: {today}
    
    [수집된 글로벌 뉴스]
    {fin_data.get('raw_news', '')}
    
    [최근 3개월 내 10% 이상 일일 급변동 내역]
    {moves_text}
    
    [나의 핵심 관점]
    {user_issue}
    
    [🚨 핵심 지시사항: 10% 이상 급변동 사유 팩트체크 (가장 중요!)]
    1. 위 [급변동 내역]에 날짜가 있다면, 그 날짜에 왜 주가가 10% 이상 폭등/폭락했는지 '구체적인 팩트'를 무조건 찾아내세요.
    2. 수집된 최신 뉴스에 그 날짜의 내용이 없다고 변명하지 마세요! 당신의 내부 사전 학습 지식을 총동원하여, 당시의 핵심 촉매제(예: 실적 발표일의 어닝 서프라이즈 여부, 아마존/AWS/Azure 파트너십 발표, 제품 출시 등)를 무조건 찾아내서 적으세요.
    3. 각 날짜별로 중복되는 이슈는 합치고, 팩트 기반으로 3~5줄 이상 매우 상세히 서술하세요. 단순 '심리 악화' 같은 뜬구름 잡는 소리는 절대 금지합니다.
    
    [보고서 필수 목차 및 양식] - 이 양식을 단 한 글자도 틀리지 말고 그대로 출력할 것.
    
    ## 🏢 {ticker} 심층 분석 보고서 - {today}
    수석 애널리스트로서, {ticker}에 대한 심층 분석 보고서를 제출합니다.
    
    ### 1. 📊 시장 위치 및 핵심 밸류체인 요약
    (이 기업의 독점적 해자와 핵심 비즈니스 모델을 3~5줄 이상 상세하고 깊이 있게 서술하세요.)
    
    ### 2. 🚨 최근 10% 이상 급변동 사유 팩트체크
    (아래 표 양식을 반드시 지키고, '구체적 촉매제' 란에 위 지시사항을 반영하여 길고 구체적인 팩트를 서술하세요. 급변동이 없다면 '최근 급변동 없음'이라고 서술하세요.)
    
    | 발생 날짜 | 종목 등락률 | 나스닥 지수 등락률 | 구체적 촉매제 (팩트 상세 기재) |
    |---|---|---|---|
    | (날짜) | (등락률) | (등락률) | (3~5줄 이상의 구체적 팩트 서술) |
    
    ### 3. 💰 실적 및 모멘텀 종합 의견
    (과거 실적 발표와 모멘텀, 빅테크 파트너십 등 구체적 호재를 종합하여 5줄 이상 전문적으로 서술하세요.)
    
    ### 4. 💡 기관 트레이딩 결론 (Actionable Insight)
    - **현재 포지션:** (롱/숏/관망 중 하나 제시 및 구체적 이유 2줄 이상)
    - **리스크 요인:** (투자 시 주의할 점 2줄 이상)
    - **최종 Action:** (구체적인 매매 조언 및 타점 전략 3줄 이상)
    """
    return ask_gemini_dynamic(prompt, [])
