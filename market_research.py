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

def get_earnings_html_via_api(ticker_symbol, df_1d, ndx):
    """lxml 에러를 원천 차단하고, 야후 JSON API에서 실적 데이터를 파싱한 뒤 주가 등락률을 계산합니다."""
    try:
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker_symbol}?modules=earningsHistory"
        session = get_robust_session()
        res = session.get(url, timeout=5)
        data = res.json()
        
        history = data.get('quoteSummary', {}).get('result', [{}])[0].get('earningsHistory', {}).get('history', [])
        
        rows = []
        for item in reversed(history): 
            date_str = item.get('quarter', {}).get('fmt', '')
            if not date_str: continue
            
            eps_est = item.get('epsEstimate', {}).get('fmt', '-')
            eps_act = item.get('epsActual', {}).get('fmt', '-')
            surp = item.get('surprisePercent', {}).get('raw', '-')
            
            surp_html = "-"
            if isinstance(surp, (int, float)):
                color = "#22c55e" if surp > 0 else "#ef4444"
                surp_html = f"<span style='color:{color}; font-weight:bold;'>{surp*100:.1f}%</span>"
            
            # 주가 및 나스닥 등락률 매칭 로직
            stock_chg = "-"
            ndx_chg = "-"
            
            try:
                # date_str (예: '2024-03-31') 을 datetime 객체로 변환하여 1D 데이터에서 검색
                dt = pd.to_datetime(date_str).tz_localize('UTC')
                # 정확한 날짜가 없으면 가장 가까운 다음 평일을 찾음
                if dt not in df_1d.index:
                    future_dates = df_1d.index[df_1d.index >= dt]
                    if not future_dates.empty: dt = future_dates[0]
                
                if dt in df_1d.index:
                    s_ret = df_1d.loc[dt, 'Daily_Return']
                    n_ret = ndx.loc[dt, 'Daily_Return']
                    
                    if isinstance(s_ret, pd.Series): s_ret = s_ret.iloc[0]
                    if isinstance(n_ret, pd.Series): n_ret = n_ret.iloc[0]
                    
                    s_color = "#22c55e" if s_ret > 0 else "#ef4444"
                    n_color = "#22c55e" if n_ret > 0 else "#ef4444"
                    
                    stock_chg = f"<span style='color:{s_color}; font-weight:bold;'>{s_ret:+.2f}%</span>"
                    ndx_chg = f"<span style='color:{n_color}; font-weight:bold;'>{n_ret:+.2f}%</span>"
            except Exception:
                pass
            
            rows.append(f"<tr><td>{date_str}</td><td>{eps_est}</td><td>{eps_act}</td><td>{surp_html}</td><td>{stock_chg}</td><td>{ndx_chg}</td></tr>")
            
        if not rows:
            return f"<div style='padding: 10px; color: #64748b;'>데이터 제공사(Yahoo)에서 해당 종목의 과거 실적 데이터를 제공하지 않습니다.</div>"
            
        html = "<table class='ma-table'><tr><th>발표일(분기)</th><th>예상치</th><th>실측치</th><th>서프라이즈</th><th>발표일 주가 변동</th><th>나스닥 변동</th></tr>"
        html += "".join(rows)
        html += "</table>"
        return html
    except Exception as e:
        return f"<div style='padding: 10px; color: #ef4444;'>실적 데이터 파싱 오류: {str(e)}</div>"

def fetch_financial_data(ticker_symbol):
    """야후 파이낸스 데이터를 크롤링하고 고급 UI/UX로 지표를 포맷팅합니다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        market_cap = info.get('marketCap', 0)
        
        # 5년치 데이터를 불러와서 과거 실적 발표일 매칭에 활용
        df_1d = ticker.history(period="5y", interval="1d")
        ndx = yf.Ticker("^IXIC").history(period="5y", interval="1d")
        df_1h = ticker.history(period="730d", interval="1h")
        
        if df_1d.empty or df_1h.empty:
            return {"error": "차트 데이터를 가져올 수 없습니다."}
            
        # Daily Return 계산 (실적 매칭 및 급변동 스캔용)
        df_1d.index = pd.to_datetime(df_1d.index, utc=True).normalize()
        ndx.index = pd.to_datetime(ndx.index, utc=True).normalize()
        
        df_1d['Daily_Return'] = df_1d['Close'].pct_change() * 100
        ndx['Daily_Return'] = ndx['Close'].pct_change() * 100
            
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
        
        # 💡 고민 3번 한 디자인: Flexbox UI Row 구조 적용
        ma_html = "<div class='metric-row'><span class='metric-label'>상태</span><span class='metric-value'>크로스 없음</span></div>"
        
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
            ma_html = f"""
            <div class='metric-row'>
                <span class='metric-label'>상태</span>
                <span class='metric-value' style='color:{color};'>{cross_name}</span>
            </div>
            <div class='metric-row'>
                <span class='metric-label'>발생일</span>
                <span class='metric-value'>{last_cross_date}</span>
            </div>
            <div class='metric-row'>
                <span class='metric-label'>당시 주가</span>
                <span class='metric-value'>${merged.loc[latest_idx, 'Close']:.2f}</span>
            </div>
            """
            
        ret_1m = ((current_price - df_1d['Close'].iloc[-21]) / df_1d['Close'].iloc[-21]) * 100 if len(df_1d) > 21 else 0
        ret_3m = ((current_price - df_1d['Close'].iloc[-63]) / df_1d['Close'].iloc[-63]) * 100 if len(df_1d) > 63 else 0
        
        momentum_html = f"""
        <div class='metric-row'>
            <span class='metric-label'>현재가</span>
            <span class='metric-value'>${current_price:.2f}</span>
        </div>
        <div class='metric-row'>
            <span class='metric-label'>1개월 변동</span>
            <span class='metric-value' style='color: {'#22c55e' if ret_1m>0 else '#ef4444'};'>{ret_1m:+.2f}%</span>
        </div>
        <div class='metric-row'>
            <span class='metric-label'>3개월 변동</span>
            <span class='metric-value' style='color: {'#22c55e' if ret_3m>0 else '#ef4444'};'>{ret_3m:+.2f}%</span>
        </div>
        """

        # 최근 90일 급변동(10% 이상) 스캔
        cutoff_date = df_1d.index[-1] - pd.Timedelta(days=90)
        last_90_days = df_1d[df_1d.index >= cutoff_date]
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
        
        # 실적 테이블 (LXML 없이 순수 JSON 우회 + 변동률 계산 적용)
        earnings_html = get_earnings_html_via_api(ticker_symbol, df_1d, ndx)
        
        # 뉴스 데이터 수집
        news_items = ticker.news
        news_lines = []
        if news_items:
            for n in news_items[:10]:
                title = n.get('title', '')
                if not title: title = n.get('content', {}).get('title', '')
                pub_time = n.get('providerPublishTime', 0)
                date_str = pd.to_datetime(pub_time, unit='s').strftime('%Y-%m-%d') if pub_time else "날짜미상"
                publisher = n.get('publisher', '알 수 없음')
                if title: news_lines.append(f"- [{date_str} / {publisher}] {title}")
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
    """AI에게 객관성(비판적 시각)과 출처 명기를 강제하는 강력한 프롬프트"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    moves_text = ""
    moves = fin_data.get("big_moves", [])
    if moves:
        for m in moves:
            moves_text += f"- 발생일: {m['date']}, 종목 등락률: {m['ticker_move']}, 나스닥 등락률: {m['ndx_move']}\n"
    else:
        moves_text = "최근 3개월 내 10% 이상 일일 급변동 없음."

    prompt = f"""
    당신은 월스트리트의 수석 기관 애널리스트입니다. 아래 데이터를 바탕으로 완벽한 투자 분석 보고서를 작성하세요.
    
    [분석 대상]
    - 종목: {ticker} (섹터: {sector})
    - 기준일: {today}
    
    [수집된 글로벌 뉴스 및 출처]
    {fin_data.get('raw_news', '')}
    
    [최근 3개월 내 10% 이상 급변동 내역]
    {moves_text}
    
    [나의 핵심 관점]
    {user_issue}
    
    [🚨 핵심 지시사항 (3번 이상 검토할 것!)]
    1. **객관성과 비판적 시각 유지:** 무조건 긍정적으로만 서술하지 마세요. 최근 경쟁 심화, 밸류에이션 부담, 실적 우려 등 '부정적인 악재'도 꼬집어 객관적으로 분석하세요.
    2. **출처 강제:** 뉴스와 관련된 내용을 적을 때는 반드시 제공된 데이터의 [발행일 / 언론사] 등 명확한 출처를 문장에 포함시키세요.
    3. **급변동 팩트체크 (가장 중요):** 위 [급변동 내역] 표에 날짜가 있다면, 그 날짜에 왜 주가가 폭락/폭등했는지 네 머릿속을 총동원하여 '진짜 핵심 촉매제(예: 실적, 아마존 등 빅테크 파트너십, 가이던스 하향)'를 무조건 찾아내서 적으세요.
    4. 모든 항목은 반드시 **3~5줄 이상 길고 상세하게** 작성하세요.
    
    [보고서 필수 마크다운 양식] - 단 한 글자도 틀리지 말고 이 구조로 출력하세요.
    
    ## 🏢 {ticker} 심층 분석 보고서 ({today} 기준)
    
    ### 1. 📊 시장 위치 및 핵심 밸류체인 요약
    (이 기업의 독점적 해자와 핵심 비즈니스 모델, 그리고 현재 직면한 시장의 리스크를 3~5줄 이상 상세히 서술하세요.)
    
    ### 2. 🚨 최근 10% 이상 급변동 사유 팩트체크
    (아래 표 양식을 지키고, 급변동이 없다면 '최근 급변동 없음'이라고 서술하세요. 구체적 촉매제 항목을 길고 구체적으로 적으세요.)
    | 발생 날짜 | 종목 등락률 | 나스닥 등락률 | 구체적 촉매제 (팩트 상세 기재) |
    |---|---|---|---|
    | (날짜) | (등락률) | (등락률) | (3~5줄 이상의 구체적 호재/악재 서술) |
    
    ### 3. 💰 실적 및 모멘텀 종합 의견 (비판적 시각 포함)
    (과거 실적 발표와 모멘텀을 뉴스 출처와 함께 5줄 이상 서술하며, 너무 긍정적인 전망은 피하고 객관적으로 서술하세요.)
    
    ### 4. 💡 기관 트레이딩 결론 (Actionable Insight)
    - **현재 포지션:** (롱/숏/관망 중 하나 제시 및 이유)
    - **리스크 요인:** (투자 시 반드시 주의해야 할 치명적 약점 2~3줄)
    - **최종 Action:** (단기/장기 대응 전략 및 구체적인 매매 조언 3~4줄)
    """
    return ask_gemini_dynamic(prompt, [])
