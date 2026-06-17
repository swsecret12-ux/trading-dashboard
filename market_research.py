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

def get_earnings_html_via_api(ticker_symbol, df_1d, ndx):
    """야후 파이낸스 실적 발표일의 주가/나스닥 변동치를 완벽하게 추적하는 테이블 렌더러"""
    try:
        ticker = yf.Ticker(ticker_symbol)
        ed = ticker.earnings_dates
        
        if ed is None or ed.empty:
            return "<div style='padding: 10px; color: #ef4444;'>해당 종목의 실적 데이터가 업데이트되지 않았습니다.</div>"
            
        rows = []
        now = pd.Timestamp.utcnow()
        
        for dt, row in ed.iterrows():
            date_str = dt.strftime('%Y-%m-%d')
            eps_est = row.get('EPS Estimate', float('nan'))
            eps_act = row.get('Reported EPS', float('nan'))
            surp = row.get('Surprise(%)', float('nan'))
            
            eps_est_str = f"{eps_est:.2f}" if pd.notna(eps_est) else "-"
            eps_act_str = f"{eps_act:.2f}" if pd.notna(eps_act) else "-"
            
            if pd.notna(surp):
                color = "#22c55e" if surp > 0 else "#ef4444"
                surp_str = f"<span style='color:{color}; font-weight:bold;'>{surp*100:.1f}%</span>"
            else:
                surp_str = "-"
                
            stock_chg = "-"
            ndx_chg = "-"
            
            if dt < now:
                search_dt = dt.normalize()
                if search_dt in df_1d.index:
                    s_ret = df_1d.loc[search_dt, 'Daily_Return']
                    if isinstance(s_ret, pd.Series): s_ret = s_ret.iloc[0]
                    s_color = "#22c55e" if s_ret > 0 else "#ef4444"
                    stock_chg = f"<span style='color:{s_color}; font-weight:bold;'>{s_ret:+.2f}%</span>"
                    
                if search_dt in ndx.index:
                    n_ret = ndx.loc[search_dt, 'Daily_Return']
                    if isinstance(n_ret, pd.Series): n_ret = n_ret.iloc[0]
                    n_color = "#22c55e" if n_ret > 0 else "#ef4444"
                    ndx_chg = f"<span style='color:{n_color}; font-weight:bold;'>{n_ret:+.2f}%</span>"
                    
                rows.append(f"<tr><td>{date_str}</td><td>{eps_est_str}</td><td>{eps_act_str}</td><td>{surp_str}</td><td>{stock_chg}</td><td>{ndx_chg}</td></tr>")
            else:
                rows.append(f"<tr style='background-color:#fffbea;'><td>⏳ {date_str} (예정)</td><td>{eps_est_str}</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>")
                
        html = "<table class='ma-table'><tr><th>발표일(분기)</th><th>예상 EPS</th><th>실측 EPS</th><th>서프라이즈</th><th>종목 발표일 등락</th><th>나스닥 발표일 등락</th></tr>"
        html += "".join(rows[:8])
        html += "</table>"
        return html
    except Exception as e:
        return f"<div style='padding: 10px; color: #ef4444;'>실적 데이터 파싱 오류: {str(e)}</div>"

def get_momentum_html(current_price, df_1d, ndx):
    """1일~3년까지의 세밀한 가격 모멘텀 비교 표 생성"""
    periods = {"1일": 1, "1개월": 21, "3개월": 63, "6개월": 126, "1년": 252, "3년": 756}
    rows = []
    
    for label, days in periods.items():
        if len(df_1d) > days and len(ndx) > days:
            past_s = df_1d['Close'].iloc[-(days+1)]
            s_ret = ((current_price - past_s) / past_s) * 100
            
            n_curr = ndx['Close'].iloc[-1]
            n_past = ndx['Close'].iloc[-(days+1)]
            n_ret = ((n_curr - n_past) / n_past) * 100
            
            s_color = "#22c55e" if s_ret > 0 else "#ef4444"
            n_color = "#22c55e" if n_ret > 0 else "#ef4444"
            
            rows.append(f"<tr><td><b>{label}</b></td><td>${past_s:.2f} &rarr; ${current_price:.2f}</td><td><span style='color:{s_color}; font-weight:bold;'>{s_ret:+.2f}%</span></td><td><span style='color:{n_color}; font-weight:bold;'>{n_ret:+.2f}%</span></td></tr>")
        else:
            rows.append(f"<tr><td><b>{label}</b></td><td style='color:#94a3b8;'>상장 기간 부족</td><td>-</td><td>-</td></tr>")
            
    html = "<table class='ma-table'><tr><th>기간</th><th>종목 가격 변화</th><th>종목 수익률</th><th>나스닥 수익률</th></tr>"
    html += "".join(rows)
    html += "</table>"
    return html

def fetch_financial_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        market_cap = info.get('marketCap', 0)
        
        df_1d = ticker.history(period="5y", interval="1d")
        ndx = yf.Ticker("^IXIC").history(period="5y", interval="1d")
        df_1h = ticker.history(period="730d", interval="1h")
        
        if df_1d.empty or df_1h.empty:
            return {"error": "차트 데이터를 가져올 수 없습니다."}
            
        df_1d.index = pd.to_datetime(df_1d.index, utc=True).normalize()
        ndx.index = pd.to_datetime(ndx.index, utc=True).normalize()
        
        df_1d['Daily_Return'] = df_1d['Close'].pct_change() * 100
        ndx['Daily_Return'] = ndx['Close'].pct_change() * 100
            
        current_price = df_1d['Close'].iloc[-1]
        
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
            
            ma_html = f"<div class='metric-row'><span class='metric-label'>상태</span><span class='metric-value' style='color:{color};'>{cross_name}</span></div><div class='metric-row'><span class='metric-label'>발생일</span><span class='metric-value'>{last_cross_date}</span></div><div class='metric-row'><span class='metric-label'>당시 주가</span><span class='metric-value'>${merged.loc[latest_idx, 'Close']:.2f}</span></div>"
            
        momentum_html = get_momentum_html(current_price, df_1d, ndx)
        
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
            except: ndx_move = 0.0
            move_records.append({"date": date_str, "ticker_move": f"{move_pct:+.1f}%", "ndx_move": f"{ndx_move:+.1f}%"})
        
        earnings_html = get_earnings_html_via_api(ticker_symbol, df_1d, ndx)
        
        # 최신 뉴스 소스 및 퍼블리셔 정밀 파싱
        news_items = ticker.news
        news_lines = []
        if news_items:
            for n in news_items[:10]:
                title = n.get('title', '')
                if not title: title = n.get('content', {}).get('title', '')
                pub_time = n.get('providerPublishTime', 0)
                date_str = pd.to_datetime(pub_time, unit='s').strftime('%Y-%m-%d') if pub_time else "날짜미상"
                publisher = n.get('publisher', '알 수 없음')
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
    today = datetime.now().strftime('%Y-%m-%d')
    
    moves_text = ""
    moves = fin_data.get("big_moves", [])
    if moves:
        for m in moves: moves_text += f"- 발생일: {m['date']}, 종목 등락률: {m['ticker_move']}, 나스닥 등락률: {m['ndx_move']}\n"
    else: moves_text = "최근 3개월 내 10% 이상 일일 급변동 없음."

    prompt = f"""
    당신은 월스트리트의 가장 냉철하고 날카로운 수석 애널리스트입니다. 아래 데이터를 바탕으로 완벽한 투자 분석 보고서를 마크다운으로 작성하세요.
    
    [분석 대상]
    - 종목: {ticker} (섹터: {sector})
    - 기준일: {today}
    
    [수집된 글로벌 뉴스 및 출처]
    {fin_data.get('raw_news', '')}
    
    [최근 3개월 내 10% 이상 급변동 내역]
    {moves_text}
    
    [나의 핵심 관점]
    {user_issue}
    
    [🚨 핵심 지시사항 (반드시 3번 검토할 것!)]
    1. **무조건적인 긍정 금지 (비판적 시각):** 좋은 소식만 나열하지 마세요. 현재 밸류에이션 부담, 경쟁사 심화, 매크로 리스크 등 투자자가 반드시 알아야 할 '부정적 악재'를 꼬집어 객관적으로 분석하세요.
    2. **출처 명시 강제:** 뉴스를 언급할 때는 무조건 제공된 [발행일 / 출처(언론사)] 정보를 문장 안에 포함시키세요.
    3. **급변동 팩트체크 초강화:** 위 [급변동 내역] 표에 날짜가 있다면, 그 날짜에 왜 급락/급등했는지 단순 심리가 아닌 '진짜 팩트(예: 아마존/MS 협업, 어닝 서프라이즈, CEO 교체 등)'를 네 사전 지식을 모두 동원하여 찾아내서 적으세요.
    4. **모든 항목은 3~5줄 이상 상세하고 깊이 있게** 작성하세요.
    
    [보고서 필수 양식] - 아래 마크다운 구조를 단 1글자도 틀리지 말고 그대로 출력하세요.
    
    ## 🏢 {ticker} 심층 분석 보고서 ({today} 기준)
    
    ### 1. 📊 시장 위치 및 핵심 밸류체인 요약
    (이 기업의 독점적 해자와 핵심 비즈니스 모델, 그리고 직면한 시장 리스크를 3~5줄 이상 비판적으로 서술하세요.)
    
    ### 2. 🚨 최근 10% 이상 급변동 사유 팩트체크 (가장 중요)
    (구체적인 팩트와 촉매제를 중복 없이 상세히 서술하세요.)
    | 발생 날짜 | 종목 등락률 | 나스닥 등락률 | 구체적 촉매제 (팩트 기반 상세 서술) |
    |---|---|---|---|
    | (날짜) | (등락률) | (등락률) | (3~5줄 이상의 구체적 호재/악재 서술) |
    
    ### 3. 💰 실적 및 모멘텀 종합 의견 (비판적 시각 포함)
    (과거 실적 발표와 모멘텀을 뉴스 출처와 함께 5줄 이상 서술하며, 리스크 요인을 반드시 포함하세요.)
    
    ### 4. 💡 기관 트레이딩 결론 (Actionable Insight)
    - **현재 포지션:** (롱/숏/관망 중 하나 제시 및 이유)
    - **리스크 요인:** (투자 시 반드시 주의해야 할 약점 2~3줄)
    - **최종 Action:** (단기/장기 대응 전략 및 구체적 매매 조언 3~4줄)
    """
    return ask_gemini_dynamic(prompt, [])
