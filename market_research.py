import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timezone
from api_utils import ask_gemini_dynamic

def get_robust_session():
    """야후 파이낸스 접속 차단을 우회하기 위한 강력한 세션 헤더 설정"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    })
    return session

def get_earnings_html_via_json(ticker, df_1d, ndx):
    """야후 내부 JSON 서버 직결로 lxml 에러를 완전 박멸하고 실적표를 구성합니다."""
    try:
        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=earningsHistory,calendarEvents"
        session = get_robust_session()
        res = session.get(url, timeout=5)
        data = res.json()
        
        result = data.get("quoteSummary", {}).get("result", [])
        if not result: return "<p style='padding:10px; color:#64748b;'>해당 종목의 실적 데이터를 불러올 수 없습니다.</p>"
        
        rows = []
        
        # 1. 미래 실적 (예정일)
        cal = result[0].get("calendarEvents", {}).get("earnings", {})
        future_date = cal.get("earningsDate", [{}])[0].get("fmt", "") if cal.get("earningsDate") else ""
        future_est = cal.get("earningsAverage", {}).get("fmt", "-")
        
        if future_date:
            rows.append(f"<tr style='background-color:#fffbea;'><td>⏳ {future_date} (예정)</td><td>{future_est}</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>")
            
        # 2. 과거 4분기 실적 (가장 최근이 위로 오도록)
        history = result[0].get("earningsHistory", {}).get("history", [])
        for item in reversed(history):
            q_date_str = item.get("quarter", {}).get("fmt", "")
            if not q_date_str: continue
            
            act = item.get("epsActual", {}).get("fmt", "-")
            est = item.get("epsEstimate", {}).get("fmt", "-")
            surp_raw = item.get("surprisePercent", {}).get("raw", None)
            
            surp_html = "-"
            if surp_raw is not None:
                color = "#22c55e" if surp_raw > 0 else "#ef4444"
                surp_html = f"<span style='color:{color}; font-weight:bold;'>{surp_raw*100:.1f}%</span>"
                
            # 발표일 당일 종목 및 나스닥 등락률 역추적
            st_ret, ndx_ret = "-", "-"
            try:
                dt = pd.to_datetime(q_date_str).tz_localize('UTC')
                if dt in df_1d.index:
                    st_ret_val = df_1d.loc[dt, 'Daily_Return']
                    s_color = "#22c55e" if st_ret_val > 0 else "#ef4444"
                    st_ret = f"<span style='color:{s_color}; font-weight:bold;'>{st_ret_val:+.1f}%</span>"
                    
                    if dt in ndx.index:
                        ndx_ret_val = ndx.loc[dt, 'Daily_Return']
                        n_color = "#22c55e" if ndx_ret_val > 0 else "#ef4444"
                        ndx_ret = f"<span style='color:{n_color}; font-weight:bold;'>{ndx_ret_val:+.1f}%</span>"
            except: pass
            
            rows.append(f"<tr><td>{q_date_str}</td><td>{est}</td><td>{act}</td><td>{surp_html}</td><td>{st_ret}</td><td>{ndx_ret}</td></tr>")
            
        if not rows: return "<p style='padding:10px; color:#64748b;'>제공된 실적 내역이 없습니다.</p>"
            
        html = "<table class='ma-table'><tr><th>발표일(분기)</th><th>예상 EPS</th><th>실측 EPS</th><th>서프라이즈</th><th>당일 종목 등락</th><th>당일 나스닥 등락</th></tr>"
        html += "".join(rows)
        html += "</table>"
        return html
        
    except Exception as e:
        return f"<p style='padding:10px; color:#ef4444;'>실적 서버 통신 일시 오류: {str(e)}</p>"

def fetch_financial_data(ticker_symbol):
    """야후 파이낸스 데이터를 크롤링하고 지표를 계산합니다."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        market_cap = info.get('marketCap', 0)
        
        # 일봉 2년 치 데이터 확보 (수익률 계산용)
        df_1d = ticker.history(period="2y", interval="1d")
        ndx = yf.Ticker("^IXIC").history(period="2y", interval="1d")
        df_1h = ticker.history(period="730d", interval="1h")
        
        if df_1d.empty or df_1h.empty:
            return {"error": "차트 데이터를 가져올 수 없습니다."}
            
        # 시간대(timezone) 표준화 및 일일 등락률 사전 계산
        df_1d.index = pd.to_datetime(df_1d.index, utc=True).normalize()
        ndx.index = pd.to_datetime(ndx.index, utc=True).normalize()
        df_1d['Daily_Return'] = df_1d['Close'].pct_change() * 100
        ndx['Daily_Return'] = ndx['Close'].pct_change() * 100
            
        current_price = df_1d['Close'].iloc[-1]
        
        # 💡 [핵심] 4H vs 1D EMA 200 크로스 분석 (최대 3개 추출)
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
        
        # 발생한 모든 크로스 병합 후 정렬
        crosses = [{'date': d, 'type': '🟢 골든크로스', 'price': merged.loc[d, 'Close']} for d in gc.index] + \
                  [{'date': d, 'type': '🔴 데드크로스', 'price': merged.loc[d, 'Close']} for d in dc.index]
        crosses.sort(key=lambda x: x['date'], reverse=True)
        
        recent_crosses = crosses[:3] # 최대 3개 추출
        last_cross_type = "크로스 없음"
        last_cross_date = "-"
        
        if not recent_crosses:
            ma_html = "<div style='padding: 10px;'>최근 1년 내 발생한 4H/1D EMA 200 크로스가 없습니다.</div>"
        else:
            last_cross_type = recent_crosses[0]['type']
            last_cross_date = recent_crosses[0]['date'].strftime('%Y-%m-%d %H:%M')
            ma_html = "<table class='ma-table'><tr><th>상태 (최근 3회)</th><th>발생일</th><th>당시 주가</th></tr>"
            for c in recent_crosses:
                color = "#22c55e" if "골든" in c['type'] else "#ef4444"
                ma_html += f"<tr><td><span style='color:{color}; font-weight:bold;'>{c['type']}</span></td><td>{c['date'].strftime('%Y-%m-%d %H:%M')}</td><td>${c['price']:.2f}</td></tr>"
            ma_html += "</table>"
            
        # 💡 모멘텀 다중 기간(1일~1년) 표 구성
        periods = {"1일": 1, "1개월": 21, "3개월": 63, "6개월": 126, "1년": 252}
        mom_rows = []
        for label, days in periods.items():
            if len(df_1d) > days and len(ndx) > days:
                s_ret = ((current_price - df_1d['Close'].iloc[-(days+1)]) / df_1d['Close'].iloc[-(days+1)]) * 100
                n_ret = ((ndx['Close'].iloc[-1] - ndx['Close'].iloc[-(days+1)]) / ndx['Close'].iloc[-(days+1)]) * 100
                s_color = "#22c55e" if s_ret > 0 else "#ef4444"
                n_color = "#22c55e" if n_ret > 0 else "#ef4444"
                mom_rows.append(f"<tr><td><b>{label}</b></td><td><span style='color:{s_color}; font-weight:bold;'>{s_ret:+.2f}%</span></td><td><span style='color:{n_color}; font-weight:bold;'>{n_ret:+.2f}%</span></td></tr>")
        
        momentum_html = f"<div style='margin-bottom:10px; font-weight:bold;'>현재가: ${current_price:.2f}</div>"
        momentum_html += "<table class='ma-table'><tr><th>기간</th><th>종목 수익률</th><th>나스닥 수익률</th></tr>" + "".join(mom_rows) + "</table>"
        
        # 💡 최근 1년 치(365일) 10% 이상 급변동 스캔 (AI에게 보낼 팩트 자료)
        cutoff_date = df_1d.index[-1] - pd.Timedelta(days=365)
        last_1y_days = df_1d[df_1d.index >= cutoff_date]
        big_moves_df = last_1y_days[abs(last_1y_days['Daily_Return']) >= 10.0]
        
        move_records = []
        for date, row in big_moves_df.iterrows():
            try: ndx_move = ndx.loc[date]['Daily_Return']
            except: ndx_move = 0.0
            move_records.append({"date": date.strftime('%Y-%m-%d'), "ticker_move": f"{row['Daily_Return']:+.1f}%", "ndx_move": f"{ndx_move:+.1f}%"})
        
        # JSON 직결 실적 파싱
        earnings_html = get_earnings_html_via_json(ticker_symbol, df_1d, ndx)
        
        # 뉴스 소스 수집 및 출처(언론사) 명확 표기
        news_items = ticker.news
        news_lines = []
        if news_items:
            for n in news_items[:10]:
                title = n.get('title', '') or n.get('content', {}).get('title', '')
                pub_time = n.get('providerPublishTime', 0)
                date_str = pd.to_datetime(pub_time, unit='s').strftime('%Y-%m-%d') if pub_time else "최근"
                publisher = n.get('publisher', '언론사')
                if title: news_lines.append(f"- [{date_str} / 출처: {publisher}] {title}")
        raw_news = "\n".join(news_lines) if news_lines else "최근 제공된 뉴스가 없습니다."

        return {
            "market_cap": market_cap, "last_cross_type": last_cross_type, "last_cross_date": last_cross_date,
            "ma_html": ma_html, "momentum_html": momentum_html, "earnings_html": earnings_html,
            "raw_news": raw_news, "big_moves": move_records
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_issue, news_content):
    """AI에게 과거 팩트체크를 강제하는 초강력 프롬프트"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    moves_text = ""
    for m in fin_data.get("big_moves", []):
        moves_text += f"- {m['date']}: 종목 {m['ticker_move']}, 나스닥 {m['ndx_move']}\n"

    prompt = f"""
    당신은 월스트리트의 가장 냉철한 수석 애널리스트입니다. 아래 데이터를 바탕으로 완벽한 투자 분석 보고서를 마크다운으로 작성하세요.
    
    [분석 대상]: {ticker} (섹터: {sector}, 기준일: {today})
    
    [최근 수집된 뉴스 - 주의: 최근 1주일치만 제공됨!]
    {fin_data.get('raw_news', '')}
    
    [최근 1년 내 10% 이상 급변동 날짜 (🚨 팩트체크 필수 영역)]
    {moves_text if moves_text else "최근 1년 내 10% 이상 일일 급변동 없음."}
    
    [나의 핵심 관점]: {user_issue}
    
    [🚨 핵심 지시사항 (반드시 지킬 것!)]
    1. **과거 팩트체크 초강제:** 제공된 뉴스는 최근 1주일치 뿐입니다. 따라서 위 [1년 내 급변동 날짜]에 발생한 엄청난 상승/하락의 이유는 뉴스 텍스트에 없습니다! **반드시 당신의 방대한 내부 학습 지식을 100% 동원하여, 해당 날짜에 무슨 일(예: SNOW의 경우 아마존 AWS 파트너십, 어닝 서프라이즈, 가이던스 폭락 등)이 있었는지 진짜 촉매제를 찾아내 상세히 적으세요.** 뉴스에 없다고 모른다고 하면 절대 안 됩니다.
    2. **비판적 시각 유지:** 무조건적인 긍정을 금지합니다. 밸류에이션 부담, 매크로 리스크, 경쟁사 위협을 꼬집어 객관적으로 분석하세요.
    3. **출처 표기:** 뉴스를 인용할 땐 반드시 [날짜 / 언론사명]을 그대로 적으세요.
    
    [보고서 필수 양식] - 아래 마크다운 구조를 단 1글자도 틀리지 말고 그대로 출력하세요.
    
    ## 🏢 {ticker} 심층 분석 보고서 ({today} 기준)
    
    ### 1. 📊 시장 위치 및 핵심 밸류체인 요약
    (비즈니스 모델 및 독점적 해자 요약)
    
    ### 2. 🚨 최근 10% 이상 급변동 사유 팩트체크 (가장 중요)
    (구체적 팩트와 촉매제를 중복 없이 상세히 서술. 당신의 사전 지식을 동원하세요!)
    | 발생 날짜 | 종목 등락률 | 나스닥 등락률 | 구체적 촉매제 (팩트 기반 상세 서술) |
    |---|---|---|---|
    | (날짜) | (등락률) | (등락률) | (아마존 파트너십, 호실적 등 구체적 이유 상세 기재) |
    
    ### 3. 💰 실적 및 모멘텀 종합 의견 (비판적 시각 포함)
    (과거 핵심 이슈와 모멘텀을 결합하여 서술하며, 리스크 요인을 반드시 포함하세요.)
    
    ### 4. 💡 기관 트레이딩 결론 (Actionable Insight)
    - **현재 포지션:** (롱/숏/관망 중 하나 제시 및 이유)
    - **리스크 요인:** (투자 시 반드시 주의해야 할 약점)
    - **최종 Action:** (구체적 매매 조언 3~4줄)
    """
    return ask_gemini_dynamic(prompt, [])
