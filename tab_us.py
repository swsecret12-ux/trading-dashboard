import streamlit as st
import pandas as pd
import requests
import re
import time
from datetime import datetime, timezone
import yfinance as yf
import streamlit.components.v1 as components

INDUSTRY_GROUPING = {
    "Semiconductors": "반도체 및 장비", "Computer Processing Hardware": "IT 하드웨어", "Computer Communications": "네트워크 통신 장비",
    "Electronic Equipment/Instruments": "IT 부품 및 전자기기", "Packaged Software": "소프트웨어 & 클라우드",
    "Internet Software/Services": "소프트웨어 & 클라우드", "Information Technology Services": "IT 서비스 & 컨설팅",
    "Internet Retail": "이커머스 & 온라인 유통", "Apparel/Footwear Retail": "의류 및 소비재 유통",
    "Specialty Stores": "전문 유통 채널", "Discount Stores": "대형 할인마트", "Pharmaceuticals: Major": "제약 & 바이오",
    "Biotechnology": "제약 & 바이오", "Medical Specialties": "의료 기기 & 장비", "Major Banks": "대형 은행",
    "Regional Banks": "지역 은행", "Investment Banks/Brokers": "투자은행 & 증권", "Finance/Rental/Leasing": "여신 전문 & 신용카드",
    "Property/Casualty Insurance": "손해보험", "Life/Health Insurance": "생명/건강보험", "Real Estate Investment Trusts": "리츠 (REITs)",
    "Broadcasting": "미디어 & 방송망", "Movies/Entertainment": "미디어 & 엔터테인먼트", "Auto Manufacturing": "자동차 & 모빌리티",
    "Motor Vehicles": "자동차 & 모빌리티", "Aerospace & Defense": "항공우주 & 국방", "Air Freight/Couriers": "항공 물류 & 택배",
    "Integrated Oil": "에너지 (석유/가스)", "Electric Utilities": "전력 & 에너지 유틸리티", "Beverages: Non-Alcoholic": "식음료 (음료 전문)",
    "Restaurants": "식음료 (F&B 프랜차이즈)", "Household/Personal Care": "가정용품 및 개인위생", "Industrial Machinery": "산업 기계 및 인프라",
    "Specialty Telecommunications": "통신 기기", "Computer Peripherals": "컴퓨터 주변기기", "Investment Managers": "투자 관리 및 펀드",
    "Other Metals/Minerals": "기타 금속 및 광물", "Managed Health Care": "의료 보험 및 헬스케어", "Trucks/Construction/Farm Machinery": "트럭 및 중장비"
}

NAME_TRANSLATIONS = {
    "AAPL": "Apple Inc. (애플)", "MSFT": "Microsoft (마이크로소프트)", "NVDA": "NVIDIA (엔비디아)",
    "GOOGL": "Alphabet Class A (구글)", "AMZN": "Amazon (아마존)", "META": "Meta Platforms (메타)", 
    "BRK-B": "Berkshire Hathaway (버크셔)", "LLY": "Eli Lilly (일라이 릴리)", "TSLA": "Tesla (테슬라)", 
    "AVGO": "Broadcom (브로드컴)", "V": "Visa (비자)", "JPM": "JPMorgan Chase (JP모건)", 
    "WMT": "Walmart (월마트)", "UNH": "UnitedHealth (유나이티드헬스)", "MA": "Mastercard (마스터카드)", 
    "PG": "Procter & Gamble (P&G)", "JNJ": "Johnson & Johnson (존슨앤드존슨)", "HD": "Home Depot (홈디포)", 
    "COST": "Costco (코스트코)", "MRK": "Merck & Co. (머크)", "ABBV": "AbbVie (애브비)", 
    "CRM": "Salesforce (세일즈포스)", "AMD": "Advanced Micro Devices (AMD)", "NFLX": "Netflix (넷플릭스)", 
    "KO": "Coca-Cola (코카콜라)", "PEP": "PepsiCo (펩시코)", "DIS": "Walt Disney (디즈니)", 
    "CSCO": "Cisco Systems (시스코)", "ADBE": "Adobe (어도비)", "QCOM": "Qualcomm (퀄컴)", 
    "INTC": "Intel (인텔)", "ARM": "ARM Holdings (암 홀딩스)", "PLTR": "Palantir (팔란티어)", 
    "RTX": "RTX Corporation (레이시온)", "PFE": "Pfizer (화이자)", "ORCL": "Oracle (오라클)", 
    "BAC": "Bank of America (뱅크오브아메리카)", "MS": "Morgan Stanley (모건스탠리)", 
    "GS": "Goldman Sachs (골드만삭스)", "WFC": "Wells Fargo (웰스파고)", "C": "Citigroup (씨티그룹)",
    "MU": "Micron Technology (마이크론)", "TSM": "Taiwan Semiconductor (TSMC)"
}

def format_mcap_krw(usd_val):
    try:
        val = float(usd_val)
        if val <= 0: return "-"
        krw_val = val * 1380
        if krw_val >= 1e12: 
            trillion = krw_val / 1e12
            t_part = int(trillion)
            b_part = int((trillion - t_part) * 10000)
            if t_part == 0: return f"{b_part:,}억원"
            if b_part == 0: return f"{t_part:,}조원"
            return f"{t_part:,}조 {b_part:,}억원"
        elif krw_val >= 1e8: 
            billion = krw_val / 1e8
            return f"{int(billion):,}억원"
        return "-"
    except:
        return usd_val

def render_us_map_tab():
    if "sp100_state_df" not in st.session_state:
        st.session_state.sp100_state_df = pd.DataFrame()

    st.markdown("### 🇺🇸 미국 시총 상위 Top 100 기업 (실시간 데이터 기준)")
    st.info("💡 **알림:** 실시간 트레이딩뷰(TradingView) 서버에서 진성 미국 시가총액 100위 명단을 즉시 스캔하여 줄을 세웁니다.")

    if st.button("🔄 실시간 순수 미국 시총 Top 100 스캔 시작", type="primary", key="us_btn"):
        with st.spinner("미국 시장 전 종목을 스캔하여 실시간 시총 100위를 선별 중입니다... (약 2초 소요)"):
            try:
                url = "https://scanner.tradingview.com/america/scan"
                payload = {
                    "filter": [
                        {"left": "market_cap_basic", "operation": "nempty"},
                        {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
                        {"left": "exchange", "operation": "in_range", "right": ["AMEX", "NASDAQ", "NYSE"]} 
                    ],
                    "options": {"lang": "en"},
                    "markets": ["america"],
                    "symbols": {"query": {"types": []}, "tickers": []},
                    "columns": ["name", "description", "sector", "industry", "market_cap_basic"],
                    "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                    "range": [0, 250] 
                }
                headers = {"User-Agent": "Mozilla/5.0"}
                res = requests.post(url, json=payload, headers=headers)
                data = res.json()
                
                df_list = []
                seen_tickers = set()
                target_exact = ['JPM', 'ORCL', 'BAC', 'MS', 'GS', 'WFC', 'C']
                
                for item in data.get('data', []):
                    if len(df_list) >= 100: break
                    sym = item['d'][0] 
                    name_raw = item['d'][1]
                    ind_raw = item['d'][3]
                    mcap = item['d'][4]
                    base_ticker = re.split(r'[-/.]', sym)[0]
                    if base_ticker == 'BML': continue
                    if base_ticker in target_exact:
                        if sym != base_ticker: continue 
                    if base_ticker in ['GOOG', 'GOOGL', 'GOOGM', 'GOOGN']: 
                        base_ticker = 'GOOG'
                        if sym not in ['GOOG', 'GOOGL']: continue
                    if base_ticker in ['BRK.A', 'BRK.B', 'BRK']: base_ticker = 'BRK' 
                    if base_ticker in ['FOXA', 'FOX']: base_ticker = 'FOX'
                    if base_ticker in ['NWSA', 'NWS']: base_ticker = 'NWS'
                    if base_ticker in ['UAA', 'UA']: base_ticker = 'UA'
                    if base_ticker in seen_tickers: continue
                    seen_tickers.add(base_ticker)
                    
                    sym_clean = sym.replace('.', '-').replace('/', '-')
                    ind_trans = INDUSTRY_GROUPING.get(ind_raw, ind_raw) 
                    name_trans = NAME_TRANSLATIONS.get(sym_clean, name_raw) 
                    
                    df_list.append({
                        '순위': len(df_list) + 1,
                        '시총': format_mcap_krw(mcap),
                        'Symbol': sym_clean,
                        'Name': name_trans,
                        '산업군(Industry)': ind_trans,
                        '시가총액_num': mcap,
                        '분야 순위': "-",
                        '크로스 상태 (4H/1D EMA200)': "대기 중",
                        '크로스 날짜': "-",
                        '크로스 당시 주가': "-",
                        '업데이트 날짜': "-"
                    })
                
                new_df = pd.DataFrame(df_list)
                new_df['분야 내 순위'] = new_df.groupby('산업군(Industry)')['시가총액_num'].rank(ascending=False, method='min')
                new_df['분야 순위'] = new_df['분야 내 순위'].apply(lambda x: f"산업 {int(x)}위" if pd.notna(x) else "-")
                new_df = new_df.drop(columns=['분야 내 순위'])
                
                st.session_state.sp100_state_df = new_df
                st.success("✅ 실시간 미국 시총 Top 100 리스트 업데이트 완료!")
            except Exception as e:
                st.error(f"데이터 스캔 중 오류가 발생했습니다: {e}")

    if not st.session_state.sp100_state_df.empty:
        st.markdown("#### 🗺️ S&P 500 주도주 히트맵 (실시간 자금 흐름)")
        st.caption("💡 블록의 크기는 시가총액(Market Cap)을, 색상은 오늘 하루의 등락률을 나타냅니다. 마우스를 올리면 상세 정보를 볼 수 있습니다.")
        heatmap_widget = """
        <div class="tradingview-widget-container" style="height: 700px; width: 100%;">
          <div class="tradingview-widget-container__widget" style="height: 100%; width: 100%;"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js" async>
          {
          "exchanges": ["NYSE", "NASDAQ", "AMEX"],
          "dataSource": "SPX500",
          "grouping": "sector",
          "blockSize": "market_cap_basic",
          "blockColor": "change",
          "locale": "kr",
          "symbolUrl": "",
          "colorTheme": "light",
          "hasTopBar": false,
          "isDataSetEnabled": false,
          "isZoomEnabled": true,
          "hasSymbolTooltip": true,
          "width": "100%",
          "height": 700
        }
          </script>
        </div>
        """
        components.html(heatmap_widget, height=700)
        st.markdown("---")
        
        # 💡 에러 박멸: 무적의 yfinance 다운로드 로직 적용
        st.markdown("#### 📈 나스닥 100 기간별 수익률 지표")
        try:
            sp500_df = pd.DataFrame()
            for tkr in ["^NDX", "QQQ"]:
                for _ in range(3): # 최대 3번 끈질기게 재시도
                    try:
                        temp_df = yf.download(tkr, period="4y", interval="1d", progress=False)
                        if not temp_df.empty:
                            if isinstance(temp_df.columns, pd.MultiIndex):
                                sp500_df = pd.DataFrame({'Close': temp_df['Close'].iloc[:, 0]})
                            else:
                                sp500_df = temp_df[['Close']]
                            break
                    except: time.sleep(1)
                if not sp500_df.empty: break

            if not sp500_df.empty:
                close_series = sp500_df['Close']
                curr = close_series.iloc[-1]
                def ret(days):
                    if len(close_series) > days: return float((curr - close_series.iloc[-(days+1)]) / close_series.iloc[-(days+1)] * 100)
                    return 0.0
                ndx_data = {"1일": ret(1), "7일": ret(5), "1개월": ret(21), "3개월": ret(63), "6개월": ret(126), "1년": ret(252), "3년": ret(756)}
                ndx_df = pd.DataFrame([ndx_data])
                def color_val(val):
                    color = '#ef4444' if val < 0 else '#22c55e'
                    return f"color: {color}; font-weight: bold;"
                formatted_df = ndx_df.map(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)
                st.dataframe(formatted_df.style.map(lambda x: color_val(float(str(x).replace('%', '')))), use_container_width=True, hide_index=True)
            else: st.warning("야후 파이낸스 통신망 일시 지연. 새로고침을 눌러주세요.")
        except Exception as e: st.error(f"데이터를 불러오는 중 오류 발생: {e}")
            
        st.markdown("#### 📊 나스닥 100 (US TECH 100 CASH) 최근 1년 흐름 (주봉 실시간 차트)")
        ndx_tv_widget = """
        <div class="tradingview-widget-container" style="height:350px;width:100%;">
          <div id="tradingview_ndx" style="height:calc(100% - 32px);width:100%"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({
          "autosize": true, "symbol": "OANDA:NAS100USD", "interval": "W", "timezone": "Etc/UTC",
          "theme": "light", "style": "1", "locale": "kr", "enable_publishing": false,
          "hide_top_toolbar": true, "hide_legend": true, "save_image": false,
          "container_id": "tradingview_ndx"
          });
          </script>
        </div>
        """
        components.html(ndx_tv_widget, height=350)
        st.markdown("---")

        symbols = st.session_state.sp100_state_df['Symbol'].tolist()
        chunks = [symbols[i:i+25] for i in range(0, 100, 25)]
        labels = ["1위~25위", "26위~50위", "51위~75위", "76위~100위"]
        st.caption("야후 파이낸스 데이터 차단(Rate Limit)을 방지하기 위해 25개 종목씩 나누어 '4시간봉 EMA 200 vs 1일봉 EMA 200' 크로스 현황을 정밀 스캔합니다.")
        cols = st.columns(4)
        for i in range(4):
            if i < len(chunks):
                if cols[i].button(f"🚀 {labels[i]} 스캔", use_container_width=True, key=f"btn_us_scan_{i}"):
                    with st.spinner(f"{labels[i]} 실시간 데이터 스캔 중..."):
                        time.sleep(2)
                        try:
                            data_1d_raw = yf.download(chunks[i], period="2y", interval="1d", progress=False)
                            data_1h_raw = yf.download(chunks[i], period="730d", interval="1h", progress=False)
                            
                            if 'Close' in data_1d_raw: data_1d = data_1d_raw['Close']
                            else: data_1d = data_1d_raw
                            if 'Close' in data_1h_raw: data_1h = data_1h_raw['Close']
                            else: data_1h = data_1h_raw
                            if isinstance(data_1d, pd.Series): data_1d = data_1d.to_frame(name=chunks[i][0])
                            if isinstance(data_1h, pd.Series): data_1h = data_1h.to_frame(name=chunks[i][0])
                            current_update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            
                            for sym in chunks[i]:
                                if sym not in data_1d.columns or sym not in data_1h.columns: c_type, c_date, c_price = "데이터 부족", "-", "-"
                                else:
                                    df_sym_1d = data_1d[sym].dropna()
                                    df_sym_1h = data_1h[sym].dropna()
                                    if len(df_sym_1d) < 150 or len(df_sym_1h) < 150: c_type, c_date, c_price = "상장기간 부족", "-", "-"
                                    else:
                                        df_1d_ma = pd.DataFrame({'Close': df_sym_1d})
                                        df_1d_ma['EMA200_1D'] = df_1d_ma['Close'].ewm(span=200, adjust=False).mean()
                                        df_1h_ma = pd.DataFrame({'Close': df_sym_1h})
                                        df_4h_ma = df_1h_ma.resample('4h').agg({'Close': 'last'}).dropna()
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
                                        
                                        if not gc.empty or not dc.empty:
                                            last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize('UTC')
                                            last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize('UTC')
                                            latest_idx = max(last_gc, last_dc)
                                            c_type = "🟢 골든크로스" if latest_idx == last_gc else "🔴 데드크로스"
                                            days_diff = (datetime.now(timezone.utc) - latest_idx).days
                                            if days_diff <= 90: c_type = f"🔥 {c_type}"
                                            c_date = latest_idx.strftime('%Y-%m-%d %H:%M')
                                            c_price = f"${merged.loc[latest_idx, 'Close']:.2f}"
                                        else:
                                            c_type, c_date, c_price = "최근 1년 내 크로스 없음", "-", "-"
                                
                                mask = st.session_state.sp100_state_df['Symbol'] == sym
                                st.session_state.sp100_state_df.loc[mask, '크로스 상태 (4H/1D EMA200)'] = c_type
                                st.session_state.sp100_state_df.loc[mask, '크로스 날짜'] = c_date
                                st.session_state.sp100_state_df.loc[mask, '크로스 당시 주가'] = c_price
                                st.session_state.sp100_state_df.loc[mask, '업데이트 날짜'] = current_update_time
                            st.success(f"✅ {current_update_time} 기준, {labels[i]} 크로스 분석 완료!")
                            st.rerun() 
                        except Exception as e:
                            st.error(f"야후 파이낸스 스캔 중 오류 발생 (잠시 후 다시 시도해주세요): {str(e)}")

        display_cols = ['순위', '시총', 'Symbol', 'Name', '산업군(Industry)', '분야 순위', '크로스 상태 (4H/1D EMA200)', '크로스 날짜', '크로스 당시 주가', '업데이트 날짜']
        st.dataframe(st.session_state.sp100_state_df[display_cols], use_container_width=True, hide_index=True, height=1100)
