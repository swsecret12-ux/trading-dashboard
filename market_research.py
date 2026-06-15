import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
import requests
import urllib.parse

def fetch_investing_news(ticker):
    """구글 뉴스 RSS를 우회하여 최신 글로벌 기사를 긁어옵니다."""
    try:
        import xml.etree.ElementTree as ET
        query = urllib.parse.quote(f"{ticker} stock OR news")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        res = requests.get(url, timeout=5)
        root = ET.fromstring(res.text)
        news_items = []
        for item in root.findall('.//item')[:5]:
            title = item.find('title').text
            pubDate = item.find('pubDate').text
            news_items.append(f"- {title} ({pubDate})")
        return "\n".join(news_items) if news_items else "관련 글로벌 뉴스가 없습니다."
    except:
        return "글로벌 뉴스 수집 실패"

def fetch_financial_data(ticker_symbol):
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        })
        
        ticker = yf.Ticker(ticker_symbol, session=session)
        
        # 1. 시가총액 추출
        try: mcap_usd = ticker.fast_info['marketCap']
        except: mcap_usd = 0

        # 2. 일봉 데이터 기반 변동성 및 이평선 계산
        hist_1d = ticker.history(period="1y")
        if hist_1d.empty: return {"error": "차트 데이터를 불러올 수 없습니다."}
        
        current_price = float(hist_1d['Close'].iloc[-1])
        
        def calc_return_html(days):
            if len(hist_1d) > days:
                past = float(hist_1d['Close'].iloc[-(days+1)])
                pct = ((current_price - past)/past)*100
                color = "#ef4444" if pct < 0 else "#22c55e" 
                sign = "+" if pct > 0 else ""
                return f"${past:.2f} ➔ ${current_price:.2f}", f"<span style='color:{color}; font-weight:bold;'>{sign}{pct:.2f}%</span>"
            return "-", "-"
        
        v1_p, v1_pct = calc_return_html(1)
        v1w_p, v1w_pct = calc_return_html(5)
        v1m_p, v1m_pct = calc_return_html(20)
        v1q_p, v1q_pct = calc_return_html(60)
        v1y_p, v1y_pct = calc_return_html(250)

        hist_1d['EMA200_1D'] = hist_1d['Close'].ewm(span=200, adjust=False).mean()
        
        # 3. 4시간봉 vs 1일봉 크로스 로직
        hist_1h = ticker.history(period="730d", interval="1h")
        if not hist_1h.empty:
            hist_4h = hist_1h.resample('4h').agg({'Close': 'last'}).dropna()
            hist_4h['EMA200_4H'] = hist_4h['Close'].ewm(span=200, adjust=False).mean()
            
            if hist_1d.index.tz is None: hist_1d.index = hist_1d.index.tz_localize('UTC')
            else: hist_1d.index = hist_1d.index.tz_convert('UTC')
            if hist_4h.index.tz is None: hist_4h.index = hist_4h.index.tz_localize('UTC')
            else: hist_4h.index = hist_4h.index.tz_convert('UTC')
            
            df_1d_ma = hist_1d[['EMA200_1D']].dropna().sort_index()
            df_4h_ma = hist_4h[['EMA200_4H', 'Close']].dropna().sort_index()
            
            merged = pd.merge_asof(df_4h_ma, df_1d_ma, left_index=True, right_index=True, direction='backward').dropna()
            
            merged['Prev_4H'] = merged['EMA200_4H'].shift(1)
            merged['Prev_1D'] = merged['EMA200_1D'].shift(1)
            
            gc = merged[(merged['EMA200_4H'] > merged['EMA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
            dc = merged[(merged['EMA200_4H'] < merged['EMA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])]
            
            if not gc.empty or not dc.empty:
                last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize('UTC')
                last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize('UTC')
                latest_idx = max(last_gc, last_dc)
                cross_type = "🟢 골든크로스" if latest_idx == last_gc else "🔴 데드크로스"
                cross_date = latest_idx.strftime('%Y-%m-%d %H:%M')
                cross_price = f"${merged.loc[latest_idx, 'Close']:.2f}"
            else:
                cross_type, cross_date, cross_price = "최근 1년 내 크로스 없음", "-", "-"
            
            curr_4h_ema200 = f"${merged['EMA200_4H'].iloc[-1]:.2f}"
            curr_1d_ema200 = f"${merged['EMA200_1D'].iloc[-1]:.2f}"
        else:
            cross_type, cross_date, cross_price = "4H 데이터 부족", "-", "-"
            curr_4h_ema200 = "-"
            curr_1d_ema200 = f"${hist_1d['EMA200_1D'].iloc[-1]:.2f}" if not pd.isna(hist_1d['EMA200_1D'].iloc[-1]) else "-"

        # 4. 10% 이상 일일 급변동 팩트 스캔 (나스닥 동기화)
        volatility_events = []
        try:
            recent_hist = hist_1d.tail(60) # 최근 2개월(약 60거래일)
            try: 
                ndx_hist = yf.Ticker("^IXIC", session=session).history(period="6mo")
                if ndx_hist.index.tz is None: ndx_hist.index = ndx_hist.index.tz_localize('UTC')
                else: ndx_hist.index = ndx_hist.index.tz_convert('UTC')
            except: 
                ndx_hist = pd.DataFrame()
            
            for i in range(1, len(recent_hist)):
                prev_c = recent_hist['Close'].iloc[i-1]
                curr_c = recent_hist['Close'].iloc[i]
                pct_change = ((curr_c - prev_c) / prev_c) * 100
                
                if abs(pct_change) >= 10.0:
                    target_d = recent_hist.index[i]
                    date_str = target_d.strftime('%Y-%m-%d')
                    ndx_pct_str = "확인불가"
                    
                    if not ndx_hist.empty:
                        try:
                            target_d_utc = target_d.tz_convert('UTC') if target_d.tz is not None else target_d.tz_localize('UTC')
                            idx_arr = ndx_hist.index.get_indexer([target_d_utc], method='nearest')
                            if len(idx_arr) > 0 and idx_arr[0] > 0:
                                n_idx = idx_arr[0]
                                n_prev = ndx_hist['Close'].iloc[n_idx-1]
                                n_curr = ndx_hist['Close'].iloc[n_idx]
                                ndx_pct_str = f"{((n_curr - n_prev) / n_prev) * 100:+.1f}%"
                        except: pass
                    volatility_events.append(f"- 날짜: {date_str} | 종목등락: {pct_change:+.1f}% | 나스닥등락: {ndx_pct_str}")
        except: pass
        vol_text = "\n".join(volatility_events) if volatility_events else "최근 2개월 내 10% 이상 일일 급변동 없음."

        # 5. 분기 실적 (yfinance 네이티브 캘린더 추출 방식으로 에러 완전 박멸)
        earnings_html = ""
        try:
            ed_df = ticker.earnings_dates
            if ed_df is not None and not ed_df.empty:
                # 미래 실적과 과거 실적 분리
                current_date = pd.Timestamp.now(tz='UTC')
                # Index is datetime
                ed_df = ed_df.sort_index(ascending=False).head(10) # 최근 10개만
                
                edts_table = """
                <table class='ma-table' style='text-align:center;'>
                  <tr style='background-color:#f1f5f9;'>
                    <th>발표일 (분기)</th><th>시장 예상치 (EPS)</th><th>실제 발표치</th><th>서프라이즈</th>
                  </tr>
                """
                valid_count = 0
                for date_idx, row in ed_df.iterrows():
                    date_str = date_idx.strftime('%Y-%m-%d')
                    
                    eps_est = row.get('EPS Estimate', pd.NA)
                    eps_rep = row.get('Reported EPS', pd.NA)
                    surp_pct = row.get('Surprise(%)', pd.NA)
                    
                    est_str = f"{eps_est:.2f}" if pd.notna(eps_est) else "-"
                    rep_str = f"{eps_rep:.2f}" if pd.notna(eps_rep) else "-"
                    
                    surprise_html = "-"
                    if pd.notna(surp_pct):
                        surp_val = surp_pct * 100
                        scolor = "#ef4444" if surp_val < 0 else "#22c55e"
                        ssign = "+" if surp_val > 0 else ""
                        stxt = "상회" if surp_val > 0 else "하회"
                        surprise_html = f"<span style='color:{scolor}; font-weight:bold;'>{ssign}{surp_val:.1f}% {stxt}</span>"
                    
                    # 미래 날짜 시각적 분리
                    is_future = date_idx > current_date
                    row_bg = "background-color: #fffbeb;" if is_future else ""
                    date_icon = "⏳ " if is_future else ""
                    
                    edts_table += f"<tr style='{row_bg}'><td><b>{date_icon}{date_str}</b></td><td>{est_str}</td><td>{rep_str}</td><td>{surprise_html}</td></tr>"
                    valid_count += 1
                    if valid_count >= 6: break 
                        
                edts_table += "</table>"
                earnings_html = edts_table if valid_count > 0 else "<p>유효한 실적 데이터를 찾을 수 없습니다.</p>"
            else:
                earnings_html = "<p>최근 실적 데이터를 불러올 수 없습니다.</p>"
        except Exception as e: 
            earnings_html = f"<p>실적 데이터 연동 일시 오류: {str(e)}</p>"

        # 6. 뉴스 수집
        try:
            news = ticker.news
            yh_news_list = []
            if news:
                for n in news[:5]:
                    title = n.get('title', '')
                    if not title and 'content' in n: title = n['content'].get('title', '')
                    if title: yh_news_list.append(f"- {title}")
            yh_news = "\n".join(yh_news_list) if yh_news_list else "최근 야후 뉴스를 불러올 수 없습니다."
        except: yh_news = "야후 뉴스 제공 오류"
            
        inv_news = fetch_investing_news(ticker_symbol)
        raw_news = f"[Yahoo News]\n{yh_news}\n\n[Global Web News]\n{inv_news}"

        ma_html = f"""
        <table class="ma-table">
          <tr style='background-color:#f1f5f9;'><th>지표 (EMA 기준)</th><th>상태 / 가격</th><th>발생일</th></tr>
          <tr><td><b>EMA 4H/1D 크로스</b></td><td style='font-size:1.1rem; font-weight:bold;'>{cross_type}</td><td>{cross_date}</td></tr>
          <tr><td><b>크로스 당시 주가</b></td><td>{cross_price}</td><td>-</td></tr>
          <tr><td><b>현재 4시간봉 EMA 200</b></td><td>{curr_4h_ema200}</td><td>-</td></tr>
          <tr><td><b>현재 1일봉 EMA 200</b></td><td>{curr_1d_ema200}</td><td>-</td></tr>
        </table>
        """
        
        mom_html = f"""
        <table class="ma-table" style='text-align:center;'>
          <tr style='background-color:#f1f5f9;'><th>기간</th><th>과거 ➔ 현재</th><th>주가 변동률</th></tr>
          <tr><td><b>1일</b></td><td>{v1_p}</td><td>{v1_pct}</td></tr>
          <tr><td><b>1주일</b></td><td>{v1w_p}</td><td>{v1w_pct}</td></tr>
          <tr><td><b>1개월</b></td><td>{v1m_p}</td><td>{v1m_pct}</td></tr>
          <tr><td><b>1분기</b></td><td>{v1q_p}</td><td>{v1q_pct}</td></tr>
          <tr><td><b>1년</b></td><td>{v1y_p}</td><td>{v1y_pct}</td></tr>
        </table>
        """

        return {
            "market_cap": mcap_usd, "raw_news": raw_news, "ma_html": ma_html, 
            "momentum_html": mom_html, "earnings_html": earnings_html,
            "last_cross_type": cross_type, "last_cross_date": cross_date,
            "vol_events_text": vol_text
        }
    except Exception as e:
        return {"error": str(e)}

def analyze_sector_with_ai(ticker, sector, fin_data, user_input="", saveticker_text=""):
    from api_utils import ask_gemini_dynamic
    
    current_date = datetime.now().strftime('%Y년 %m월 %d일')
    
    prompt = f"""
    당신은 월스트리트의 최정상급 수석 애널리스트입니다. 
    아래의 [분석 대상 데이터]를 바탕으로, 최고 수준의 기관용 심층 리서치 리포트를 작성하세요.
    
    [분석 대상 데이터]
    - 오늘 날짜: {current_date}
    - 종목명: {ticker} (섹터: {sector})
    - 최근 2달 내 10% 이상 일일 급변동 팩트 (발생 날짜 / 종목등락률 / 당시 나스닥 등락률):
    {fin_data.get('vol_events_text')}
    - 최신 글로벌 뉴스:
    {fin_data.get('raw_news')}
    - 유저 메모: {user_input}
    
    [작성 목차 및 필수 지침 - 절대 엄수]
    * 반드시 아래의 4가지 목차와 마크다운 양식을 정확히 지켜야 합니다.
    * 밋밋하게 짧게 쓰지 말고, 각 항목별로 전문가의 시각을 담아 **최소 4~5줄 이상의 텍스트(불릿 포인트 활용)**로 풍성하게 서술하세요.

    ### 1. 🏢 시장 위치 및 핵심 밸류체인 요약
    (해당 기업의 비즈니스 모델, 독점적 지위, 파트너 생태계를 상세히 서술하세요.)
    
    ### 2. 🚨 최근 10% 이상 급변동 사유 팩트체크 (가장 중요)
    (제공된 급변동 데이터가 있다면 아래 마크다운 표를 무조건 생성하세요. 
    **[초강력 지시사항]** 뉴스 데이터에 과거 내용이 없더라도, 당신이 사전 학습한 인터넷 지식을 총동원하여 해당 날짜의 실제 촉매제(예: 실적 발표 수치, 아마존/Azure 파트너십 발표, 신제품 출시 등)를 정확히 찾아내어 '구체적 촉매제' 칸에 길고 상세하게 팩트 기반으로 적으세요. 절대 '알 수 없음'이나 '추정됨'으로 뭉뚱그리지 마세요.)
    
    | 발생 날짜 | 종목 등락률 | 나스닥 지수 등락률 | 구체적 촉매제 (팩트 상세 기재) |
    |---|---|---|---|
       
    ### 3. 💰 실적 및 모멘텀 종합 의견
    (최근 실적 발표의 핵심 수치, 마진율, 기술적 모멘텀을 심층 분석하세요.)
       
    ### 4. 💡 기관 트레이딩 결론 (Actionable Insight)
    (롱/숏/관망 중 현재 포지션을 명확히 제시하고, 목표가 상향/하향 여부 등 구체적인 액션 플랜을 4줄 이상 제시하세요.)
    """
    return ask_gemini_dynamic(prompt, [])
