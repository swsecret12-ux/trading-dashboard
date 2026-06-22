import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone
import yfinance as yf
import altair as alt

# 💡 트레이딩뷰의 어색한 직역을 매끄럽고 직관적인 한국 주식 섹터명으로 대대적 교정
INDUSTRY_GROUPING_KR = {
    "Electronic Technology": "IT & 전자", "전자 기술": "IT & 전자", 
    "Semiconductors": "반도체", "반도체": "반도체",
    "Electronic Components": "IT 부품", "전자 부품": "IT 부품", "전기 제품": "IT 부품",
    "Telecommunications Equipment": "통신 장비", "통신 장비": "통신 장비",
    "Internet Software/Services": "소프트웨어 & 인터넷", "인터넷 소프트웨어/서비스": "소프트웨어 & 인터넷", 
    "Packaged Software": "소프트웨어", "패키지 소프트웨어": "소프트웨어",
    "Information Technology Services": "IT 서비스", "정보 기술 서비스": "IT 서비스",
    "Computer Communications": "네트워크 & 통신", "컴퓨터 통신": "네트워크 & 통신",
    "Motor Vehicles": "자동차", "자동차": "자동차", "모터 차량": "자동차",
    "Auto Parts: OEM": "자동차 부품", "자동차 부품: OEM": "자동차 부품",
    "Chemicals: Major Diversified": "화학", "화학: 주요 다각화": "화학", "화학": "화학", 
    "Chemicals: Specialty": "화학", "특수 화학": "화학",
    "Pharmaceuticals: Major": "제약 & 바이오", "제약: 주요": "제약 & 바이오", 
    "Biotechnology": "제약 & 바이오", "생명공학": "제약 & 바이오",
    "Medical Specialties": "의료 기기", "의료 전문": "의료 기기",
    "Major Banks": "은행", "주요 은행": "은행", "Regional Banks": "은행", "지역 은행": "은행",
    "Investment Banks/Brokers": "증권", "투자 은행/브로커": "증권", "투자 은행/중개인": "증권",
    "Life/Health Insurance": "보험", "생명/건강 보험": "보험", 
    "Property/Casualty Insurance": "보험", "재산/상해 보험": "보험",
    "Financial Conglomerates": "기타 금융", "금융 대기업": "기타 금융", 
    "Finance/Rental/Leasing": "기타 금융", "금융/임대/리스": "기타 금융",
    "Steel": "철강", "철강": "철강", 
    "Other Metals/Minerals": "비철금속 & 광물", "기타 금속/광물": "비철금속 & 광물",
    "Marine Shipping": "조선 & 해운", "해상 운송": "조선 & 해운", "해양 해운": "조선 & 해운",
    "Aerospace & Defense": "우주항공 & 국방", "항공 우주 & 국방": "우주항공 & 국방",
    "Electric Utilities": "전력 & 에너지", "전기 유틸리티": "전력 & 에너지", 
    "Oil & Gas Production": "정유 & 가스", "석유 & 가스 생산": "정유 & 가스", 
    "Integrated Oil": "정유 & 가스", "통합 석유": "정유 & 가스",
    "Engineering & Construction": "건설 & 인프라", "엔지니어링 & 건설": "건설 & 인프라", 
    "Homebuilding": "건설 & 인프라", "주택 건설": "건설 & 인프라",
    "Food: Major Diversified": "식음료", "음식: 주요 다각화": "식음료", "식품: 주요 다각화": "식음료", 
    "Food: Specialty/Candy": "식음료", "식품: 특수/캔디": "식음료", 
    "Beverages: Non-Alcoholic": "식음료", "음료: 비알코올": "식음료",
    "Apparel/Footwear": "의류 & 소비재", "의류/신발": "의류 & 소비재", 
    "Apparel/Footwear Retail": "의류 & 소비재", "의류/신발 소매": "의류 & 소비재",
    "Specialty Stores": "유통 & 이커머스", "전문 상점": "유통 & 이커머스", 
    "Discount Stores": "유통 & 이커머스", "할인 상점": "유통 & 이커머스", 
    "Internet Retail": "유통 & 이커머스", "인터넷 소매": "유통 & 이커머스",
    "Broadcasting": "미디어 & 엔터", "방송": "미디어 & 엔터", 
    "Movies/Entertainment": "미디어 & 엔터", "영화/엔터테인먼트": "미디어 & 엔터", 
    "Advertising/Marketing Services": "광고 & 마케팅", "광고/마케팅 서비스": "광고 & 마케팅",
    "Airlines": "항공", "항공사": "항공", "Railroads": "철도", "철도": "철도",
    "Trucks/Construction/Farm Machinery": "중장비 & 기계", "트럭/건설/농기계": "중장비 & 기계", 
    "Industrial Machinery": "산업 기계", "산업 기계": "산업 기계",
    "Household/Personal Care": "생활용품", "가정/개인 관리": "생활용품",
    "Other Transportation": "물류 & 운송", "기타 운송": "물류 & 운송", 
    "Air Freight/Couriers": "물류 & 운송", "항공 화물/택배": "물류 & 운송"
}

# 💡 대한민국 주식시장의 현실에 맞춘 핵심 주도주 강제 교정 딕셔너리 (삼성, 하이닉스, 2차전지 등)
CUSTOM_TICKER_INDUSTRY = {
    "005930": "반도체", "000660": "반도체", "042700": "반도체", # 삼성전자, SK하이닉스, 한미반도체
    "373220": "2차전지", "006400": "2차전지", "096770": "2차전지", # LG엔솔, 삼성SDI, SK이노베이션
    "051910": "화학 & 2차전지", "003670": "2차전지 소재", "247540": "2차전지 소재", "086520": "2차전지 소재", # LG화학, 포스코퓨처엠, 에코프로 형제
    "005380": "자동차", "000270": "자동차", "012330": "자동차 부품", # 현대차, 기아, 현대모비스
    "207940": "제약 & 바이오", "068270": "제약 & 바이오", "000100": "제약 & 바이오", # 삼바, 셀트리온, 유한양행
    "035420": "소프트웨어 & 인터넷", "035720": "소프트웨어 & 인터넷", # 네이버, 카카오
    "005490": "철강 & 2차전지 소재", # POSCO홀딩스
    "105560": "금융지주", "055550": "금융지주", "086790": "금융지주", "316140": "금융지주", # KB, 신한, 하나, 우리
    "032830": "생명보험", "032640": "통신", "017670": "통신", "030200": "통신"
}

def format_krw_direct(krw_val):
    try:
        val = float(krw_val)
        if val <= 0: return "-"
        if val >= 1e12: 
            trillion = val / 1e12
            t_part = int(trillion)
            b_part = int((trillion - t_part) * 10000)
            if t_part == 0: return f"{b_part:,}억원"
            if b_part == 0: return f"{t_part:,}조원"
            return f"{t_part:,}조 {b_part:,}억원"
        elif val >= 1e8: 
            billion = val / 1e8
            return f"{int(billion):,}억원"
        return "-"
    except:
        return krw_val

# 등락률 %를 받아 색상을 입히는 함수
def color_pct(val):
    if isinstance(val, str) and '%' in val:
        try:
            num = float(val.replace('%', '').replace('+', ''))
            color = '#ef4444' if num < 0 else '#22c55e'
            return f'color: {color}; font-weight: bold;'
        except: pass
    return ''

def render_kr_map_tab():
    if "kospi100_state_df" not in st.session_state:
        st.session_state.kospi100_state_df = pd.DataFrame()

    st.markdown("### 🇰🇷 한국 코스피 상위 Top 100 기업 (실시간 데이터 기준)")

    if st.button("🔄 실시간 한국 코스피 Top 100 스캔 시작", type="primary"):
        with st.spinner("코스피 전 종목을 스캔하여 실시간 시총 100위를 선별 중입니다..."):
            try:
                url = "https://scanner.tradingview.com/korea/scan"
                # 💡 장기 변동성(3개월, 6개월, 1년) 데이터 추가 호출!
                payload = {
                    "filter": [
                        {"left": "market_cap_basic", "operation": "nempty"}, 
                        {"left": "type", "operation": "in_range", "right": ["stock", "dr"]}, 
                        {"left": "exchange", "operation": "in_range", "right": ["KRX"]}
                    ],
                    "options": {"lang": "ko"},
                    "markets": ["korea"],
                    "columns": ["name", "description", "sector", "industry", "market_cap_basic", "close", "change", "Perf.W", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y", "RSI"],
                    "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                    "range": [0, 200]
                }
                res = requests.post(url, json=payload, headers={"User-Agent": "Mozilla/5.0"})
                data = res.json()
                
                df_list = []
                seen_tickers = set()
                
                for item in data.get('data', []):
                    if len(df_list) >= 100: break
                    sym = item['d'][0]
                    name_raw = item['d'][1]
                    ind_raw = item['d'][3]
                    mcap = item['d'][4]
                    close_p = item['d'][5]
                    chg_1d = item['d'][6]
                    chg_1w = item['d'][7]
                    chg_1m = item['d'][8]
                    chg_3m = item['d'][9]  # 60일(3개월) 변동
                    chg_6m = item['d'][10] # 120일(6개월) 변동
                    chg_1y = item['d'][11] # 200일(1년) 변동
                    rsi_val = item['d'][12] # RSI 지표
                    
                    base_ticker = sym.split(':')[-1]
                    if (len(base_ticker) == 6 and not base_ticker.endswith('0')) or "우" in name_raw: continue
                    if base_ticker in seen_tickers: continue
                    seen_tickers.add(base_ticker)
                    
                    # 💡 산업군 번역 및 강제 교정 적용
                    if base_ticker in CUSTOM_TICKER_INDUSTRY:
                        ind_trans = CUSTOM_TICKER_INDUSTRY[base_ticker]
                    else:
                        ind_trans = INDUSTRY_GROUPING_KR.get(ind_raw, ind_raw) if ind_raw else "기타"
                    
                    # 💡 RSI가 25 미만이면 🚨 응급 이모지 추가
                    if rsi_val:
                        rsi_str = f"🚨 {rsi_val:.1f}" if rsi_val < 25 else f"{rsi_val:.1f}"
                    else:
                        rsi_str = "-"
                    
                    df_list.append({
                        '순위': len(df_list) + 1,
                        'Symbol': base_ticker,
                        'YF_Symbol': f"{base_ticker}.KS",
                        'Name': name_raw,
                        '현재주가': f"₩{close_p:,.0f}" if close_p else "-",
                        'RSI': rsi_str,
                        '1일 변동': f"{chg_1d:+.2f}%" if chg_1d else "-",
                        '7일 변동': f"{chg_1w:+.2f}%" if chg_1w else "-",
                        '30일 변동': f"{chg_1m:+.2f}%" if chg_1m else "-",
                        '60일 변동': f"{chg_3m:+.2f}%" if chg_3m else "-",
                        '120일 변동': f"{chg_6m:+.2f}%" if chg_6m else "-",
                        '200일 변동': f"{chg_1y:+.2f}%" if chg_1y else "-",
                        '산업군(Industry)': ind_trans,
                        '시가총액_num': mcap,
                        '시총': format_krw_direct(mcap),
                        '분야 순위': "-",
                        '크로스 상태 (4H/1D EMA200)': "대기 중",
                        '크로스 날짜': "-",
                        '크로스 당시 주가': "-"
                    })
                
                new_df = pd.DataFrame(df_list)
                new_df['분야 순위'] = new_df.groupby('산업군(Industry)')['시가총액_num'].rank(ascending=False, method='min').apply(lambda x: f"산업 {int(x)}위")
                st.session_state.kospi100_state_df = new_df.drop(columns=['시가총액_num'])
                st.success("✅ 업데이트 완료! (주가, 변동성 6종, RSI 데이터 포함)")
            except Exception as e: 
                st.error(f"오류: {e}")

    if not st.session_state.kospi100_state_df.empty:
        # 1. 수익률 표시
        st.markdown("#### 📈 코스피(KOSPI) 기간별 수익률 지표")
        try:
            kospi_df = pd.DataFrame()
            for _ in range(2):
                try:
                    temp_df = yf.download("^KS11", period="4y", interval="1d", progress=False)
                    if not temp_df.empty:
                        kospi_df = temp_df
                        break
                except: time.sleep(1)

            if not kospi_df.empty:
                # 💡 yfinance 최신 MultiIndex 버그 방어 코드 적용
                if isinstance(kospi_df.columns, pd.MultiIndex): 
                    close_series = kospi_df['Close'].iloc[:, 0].dropna()
                else: 
                    close_series = kospi_df['Close'].dropna()
                
                curr = close_series.iloc[-1]
                def ret(days):
                    if len(close_series) > days: return float((curr - close_series.iloc[-(days+1)]) / close_series.iloc[-(days+1)] * 100)
                    return 0.0
                
                kr_data = {"1일": ret(1), "7일": ret(5), "1개월": ret(21), "3개월": ret(63), "6개월": ret(126), "1년": ret(252), "3년": ret(756)}
                kr_df = pd.DataFrame([kr_data])
                
                formatted_df = kr_df.map(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)
                st.dataframe(formatted_df.style.map(lambda x: color_pct(str(x))), use_container_width=True, hide_index=True)
            else: 
                st.warning("야후 파이낸스 통신망 일시 지연. 새로고침을 눌러주세요.")
        except Exception as e: 
            st.warning(f"수익률 데이터 로딩 실패: {e}")

        # 2. 종합 차트 렌더링 (인터랙티브 툴팁, RSI, 거래량 포함)
        st.markdown("#### 📊 코스피 (KOSPI) 최근 1년 흐름 (일봉 종합 차트)")
        try:
            df_raw = yf.download("^KS11", period="1y", interval="1d", progress=False)
            if not df_raw.empty:
                if isinstance(df_raw.columns, pd.MultiIndex):
                    df_chart = pd.DataFrame({
                        'Open': df_raw['Open'].iloc[:, 0], 
                        'High': df_raw['High'].iloc[:, 0],
                        'Low': df_raw['Low'].iloc[:, 0], 
                        'Close': df_raw['Close'].iloc[:, 0],
                        'Volume': df_raw['Volume'].iloc[:, 0]
                    })
                else: 
                    df_chart = df_raw[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                    
                df_chart = df_chart.dropna().reset_index()
                df_chart.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']

                # RSI 계산 로직
                delta = df_chart['Close'].diff()
                df_chart['RSI'] = 100 - (100 / (1 + (delta.where(delta > 0, 0).fillna(0).rolling(14).mean() / -delta.where(delta < 0, 0).fillna(0).rolling(14).mean())))
                df_chart['RSI'] = df_chart['RSI'].fillna(50)

                min_price, max_price = df_chart['Low'].min() * 0.98, df_chart['High'].max() * 1.02
                color_condition = alt.condition("datum.Open <= datum.Close", alt.value("#089981"), alt.value("#f23645"))
                
                # 마우스 오버 툴팁용 크로스헤어 선택자
                hover = alt.selection_point(fields=['Date'], nearest=True, on='mouseover', empty=False, clear='mouseout')
                
                # 공통 X축 설정
                x_axis_hidden = alt.X('Date:O', axis=alt.Axis(labels=False, ticks=False, domain=False, title=None))
                x_axis_show = alt.X('Date:O', axis=alt.Axis(
                    labelAngle=0, labelColor='#787b86', 
                    labelExpr="indexof(datum.label, datum.value) % 20 == 0 ? timeFormat(datum.value, '%Y-%m-%d') : ''", 
                    grid=True, gridColor='#e0e3eb', gridDash=[2, 2], domain=False, ticks=False, title=None
                ))
                
                base = alt.Chart(df_chart)
                
                # 마우스를 따라다니는 투명한 포인트와 툴팁
                selectors = base.mark_point(size=100).encode(
                    x=x_axis_hidden, 
                    opacity=alt.value(0), 
                    tooltip=[
                        alt.Tooltip('Date:T', format='%Y-%m-%d', title='날짜'), 
                        alt.Tooltip('Open:Q', format=',.0f', title='시가'), 
                        alt.Tooltip('High:Q', format=',.0f', title='고가'), 
                        alt.Tooltip('Low:Q', format=',.0f', title='저가'), 
                        alt.Tooltip('Close:Q', format=',.0f', title='종가'), 
                        alt.Tooltip('Volume:Q', format=',.0f', title='거래량'), 
                        alt.Tooltip('RSI:Q', format='.2f', title='RSI')
                    ]
                ).add_params(hover)
                
                # 마우스를 따라다니는 회색 세로줄
                rules = base.mark_rule(color='#787b86', strokeWidth=1, strokeDash=[5,5]).encode(
                    x=x_axis_hidden
                ).transform_filter(hover)
                
                # 캔들 차트 본체 (높이 750으로 유지)
                candlestick_chart = (
                    base.mark_rule(size=2.0).encode(
                        x=x_axis_hidden, 
                        y=alt.Y('Low:Q', scale=alt.Scale(domain=[min_price, max_price]), axis=alt.Axis(orient='right', title='가격', format=',.0f')), 
                        y2='High:Q', 
                        color=color_condition
                    ) + 
                    base.mark_bar(size=4.0).encode(
                        x=x_axis_hidden, 
                        y='Open:Q', 
                        y2='Close:Q', 
                        color=color_condition
                    ) + 
                    selectors + 
                    rules
                ).properties(height=750)
                
                # 거래량 차트 본체
                volume_chart = (
                    base.mark_bar(size=4.0).encode(
                        x=x_axis_hidden, 
                        y=alt.Y('Volume:Q', axis=alt.Axis(orient='right', format='.2s', title='거래량')), 
                        color=color_condition
                    ) + 
                    selectors + 
                    rules
                ).properties(height=150)
                
                # RSI 차트 본체
                rsi_chart = (
                    base.mark_line(color='#673ab7', strokeWidth=2).encode(
                        x=x_axis_show, 
                        y=alt.Y('RSI:Q', scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(orient='right', title='RSI', tickCount=3))
                    ) + 
                    alt.Chart(pd.DataFrame({'y': [30, 70]})).mark_rule(strokeDash=[5,5], color='gray').encode(y='y') + 
                    selectors.encode(x=x_axis_show) + 
                    rules.encode(x=x_axis_show)
                ).properties(height=150)
                
                # 차트 병합 및 테두리/폰트 크기 설정
                combined = alt.vconcat(candlestick_chart, volume_chart, rsi_chart, spacing=0).resolve_scale(x='shared').configure_view(
                    stroke='lightgray', strokeWidth=1
                ).configure_axis(
                    labelFontSize=13, titleFontSize=13
                )
                
                st.altair_chart(combined, use_container_width=True)
        except Exception as e: 
            st.error(f"차트 불러오기 오류: {e}")

        st.markdown("---")

        # 3. 4단계 스캔
        yf_symbols = st.session_state.kospi100_state_df['YF_Symbol'].tolist()
        ui_symbols = st.session_state.kospi100_state_df['Symbol'].tolist()
        chunks_yf = [yf_symbols[i:i+25] for i in range(0, 100, 25)]
        chunks_ui = [ui_symbols[i:i+25] for i in range(0, 100, 25)]
        labels_kr = ["1위~25위", "26위~50위", "51위~75위", "76위~100위"]
        
        st.caption("야후 파이낸스 데이터 차단(Rate Limit)을 방지하기 위해 25개 종목씩 나누어 EMA 크로스 현황을 정밀 스캔합니다.")
        cols_kr = st.columns(4)
        
        for i in range(4):
            if i < len(chunks_yf):
                if cols_kr[i].button(f"🚀 코스피 {labels_kr[i]} 스캔", use_container_width=True):
                    with st.spinner("스캔 중..."):
                        try:
                            # 다운로드 및 데이터 전처리 구조 복구
                            data_1d_raw = yf.download(chunks_yf[i], period="2y", interval="1d", progress=False)
                            data_1h_raw = yf.download(chunks_yf[i], period="730d", interval="1h", progress=False)
                            
                            data_1d = data_1d_raw.get('Close', pd.DataFrame())
                            data_1h = data_1h_raw.get('Close', pd.DataFrame())
                            
                            if isinstance(data_1d, pd.Series): 
                                data_1d = data_1d.to_frame(name=chunks_yf[i][0])
                            if isinstance(data_1h, pd.Series): 
                                data_1h = data_1h.to_frame(name=chunks_yf[i][0])
                            
                            for j, yf_sym in enumerate(chunks_yf[i]):
                                ui_sym = chunks_ui[i][j]
                                c_type, c_date, c_price = "데이터 부족", "-", "-"
                                
                                if yf_sym in data_1d.columns and yf_sym in data_1h.columns:
                                    df_sym_1d = data_1d[yf_sym].dropna()
                                    df_sym_1h = data_1h[yf_sym].dropna()
                                    
                                    if len(df_sym_1d) >= 150 and len(df_sym_1h) >= 150:
                                        df_1d_ma = pd.DataFrame({'Close': df_sym_1d})
                                        df_1d_ma['EMA200_1D'] = df_1d_ma['Close'].ewm(span=200, adjust=False).mean()
                                        
                                        df_1h_ma = pd.DataFrame({'Close': df_sym_1h})
                                        df_4h_ma = df_1h_ma.resample('4h').agg({'Close': 'last'}).dropna()
                                        df_4h_ma['EMA200_4H'] = df_4h_ma['Close'].ewm(span=200, adjust=False).mean()
                                        
                                        df_1d_ma.index = pd.to_datetime(df_1d_ma.index, utc=True)
                                        df_4h_ma.index = pd.to_datetime(df_4h_ma.index, utc=True)
                                        
                                        merged = pd.merge_asof(df_4h_ma[['EMA200_4H', 'Close']], df_1d_ma[['EMA200_1D']], left_index=True, right_index=True, direction='backward').dropna()
                                        merged['Prev_4H'] = merged['EMA200_4H'].shift(1)
                                        merged['Prev_1D'] = merged['EMA200_1D'].shift(1)
                                        
                                        gc = merged[(merged['EMA200_4H'] > merged['EMA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
                                        dc = merged[(merged['EMA200_4H'] < merged['EMA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])]
                                        
                                        if not gc.empty or not dc.empty:
                                            last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize('UTC')
                                            last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize('UTC')
                                            latest_idx = max(last_gc, last_dc)
                                            
                                            c_type = "🟢 골든크로스" if latest_idx == last_gc else "🔴 데드크로스"
                                            if (datetime.now(timezone.utc) - latest_idx).days <= 90: 
                                                c_type = f"🔥 {c_type}"
                                                
                                            c_date = latest_idx.strftime('%Y-%m-%d %H:%M')
                                            c_price = f"₩{merged.loc[latest_idx, 'Close']:,.0f}"
                                        else: 
                                            c_type = "최근 1년 내 없음"
                                
                                mask = st.session_state.kospi100_state_df['Symbol'] == ui_sym
                                st.session_state.kospi100_state_df.loc[mask, '크로스 상태 (4H/1D EMA200)'] = c_type
                                st.session_state.kospi100_state_df.loc[mask, '크로스 날짜'] = c_date
                                st.session_state.kospi100_state_df.loc[mask, '크로스 당시 주가'] = c_price
                            
                            st.success(f"✅ 스캔 완료!")
                            st.rerun() 
                        except Exception as e: 
                            st.error(f"오류: {e}")

        # 4. 데이터프레임 렌더링 (💡 변동성 추가 및 극한의 너비 다이어트)
        display_cols_kr = ['순위', 'Symbol', '시총', 'Name', '산업군(Industry)', '분야 순위', '현재주가', 'RSI', '1일 변동', '7일 변동', '30일 변동', '60일 변동', '120일 변동', '200일 변동', '크로스 상태 (4H/1D EMA200)', '크로스 날짜', '크로스 당시 주가']
        
        st.dataframe(
            st.session_state.kospi100_state_df[display_cols_kr].style.map(color_pct, subset=['1일 변동', '7일 변동', '30일 변동', '60일 변동', '120일 변동', '200일 변동']),
            column_config={
                "순위": st.column_config.NumberColumn(width=40),
                "Symbol": st.column_config.TextColumn("심볼", width=50),
                "시총": st.column_config.TextColumn("시총", width=70),
                "산업군(Industry)": st.column_config.TextColumn("산업군", width=90),
                "분야 순위": st.column_config.TextColumn("분야순위", width=60),
                "현재주가": st.column_config.TextColumn("현재가", width=70),
                "RSI": st.column_config.TextColumn("RSI", width=50),
                "1일 변동": st.column_config.TextColumn("1일", width=55),
                "7일 변동": st.column_config.TextColumn("7일", width=55),
                "30일 변동": st.column_config.TextColumn("30일", width=55),
                "60일 변동": st.column_config.TextColumn("60일", width=55),
                "120일 변동": st.column_config.TextColumn("120일", width=55),
                "200일 변동": st.column_config.TextColumn("200일", width=55),
                "크로스 상태 (4H/1D EMA200)": st.column_config.TextColumn("EMA크로스", width=90),
                "크로스 날짜": st.column_config.TextColumn("크로스날짜", width=90),
                "크로스 당시 주가": st.column_config.TextColumn("크로스가", width=70)
            },
            use_container_width=True, 
            hide_index=True, 
            height=1100
        )
