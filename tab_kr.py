import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone
import yfinance as yf
import altair as alt
import streamlit.components.v1 as components

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

def render_kr_map_tab():
    if "kospi100_state_df" not in st.session_state:
        st.session_state.kospi100_state_df = pd.DataFrame()

    st.markdown("### 🇰🇷 한국 코스피 상위 Top 100 기업 (실시간 데이터 기준)")
    st.info("💡 **알림:** 실시간 트레이딩뷰(TradingView) 서버에서 대한민국 코스피(KOSPI) 시가총액 최상위 100개 명단(우선주 완전 필터링)을 즉시 스캔하여 묶어냅니다.")

    if st.button("🔄 실시간 한국 코스피 Top 100 스캔 시작", type="primary", key="btn_kr_scan"):
        with st.spinner("코스피 전 종목을 스캔하여 실시간 시총 100위를 선별 중입니다... (약 2초 소요)"):
            try:
                url = "https://scanner.tradingview.com/korea/scan"
                payload = {
                    "filter": [
                        {"left": "market_cap_basic", "operation": "nempty"},
                        {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
                        {"left": "exchange", "operation": "in_range", "right": ["KRX"]} 
                    ],
                    "options": {"lang": "ko"},
                    "markets": ["korea"],
                    "symbols": {"query": {"types": []}, "tickers": []},
                    "columns": ["name", "description", "sector", "industry", "market_cap_basic"],
                    "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                    "range": [0, 200] 
                }
                headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
                res = requests.post(url, json=payload, headers=headers)
                
                if res.status_code != 200: raise Exception(f"트레이딩뷰 서버 응답 지연 (상태 코드: {res.status_code})")
                data = res.json()
                
                df_list = []
                seen_tickers = set()
                
                for item in data.get('data', []):
                    if len(df_list) >= 100: break
                    sym = item['d'][0] 
                    name_raw = item['d'][1]
                    ind_raw = item['d'][3]
                    mcap = item['d'][4]
                    
                    base_ticker = sym.split(':')[-1]
                    
                    # 우선주 필터링
                    if len(base_ticker) == 6 and not base_ticker.endswith('0'): continue
                    if "우" in name_raw and ("우B" in name_raw or "우(" in name_raw or name_raw.endswith("우")): continue
                    
                    if base_ticker in seen_tickers: continue
                    seen_tickers.add(base_ticker)
                    yf_ticker = f"{base_ticker}.KS"
                    
                    df_list.append({
                        '순위': len(df_list) + 1,
                        '시총': format_krw_direct(mcap),
                        'Symbol': base_ticker,
                        'YF_Symbol': yf_ticker,
                        'Name': name_raw,
                        '산업군(Industry)': ind_raw if ind_raw else "기타",
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
                
                st.session_state.kospi100_state_df = new_df
                st.success("✅ 불순물 및 우선주 제거, 순수 코스피 보통주 Top 100 리스트 업데이트 완료!")
            except Exception as e:
                st.error(f"데이터 스캔 중 오류가 발생했습니다: {e}")

    if not st.session_state.kospi100_state_df.empty:
        st.markdown("#### 🗺️ 한국 코스피 주도주 히트맵 (실시간 자금 흐름)")
        st.caption("💡 블록의 크기는 시가총액(Market Cap)을, 색상은 오늘 하루의 등락률을 나타냅니다. 마우스를 올리면 상세 정보를 볼 수 있습니다.")
        
        # 💡 'market': 'south_korea'를 명시적으로 다시 추가하여 미국 시장으로 튕기는 현상 완벽 방어!
        heatmap_widget_kr = """
        <div class="tradingview-widget-container" style="height: 700px; width: 100%;">
          <div class="tradingview-widget-container__widget" style="height: 100%; width: 100%;"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js" async>
          {
          "exchanges": [],
          "dataSource": "KOSPI200",
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
          "height": 700,
          "market": "south_korea"
        }
          </script>
        </div>
        """
        components.html(heatmap_widget_kr, height=700)
        st.markdown("---")
        
        st.markdown("#### 📈 코스피(KOSPI) 기간별 수익률 지표")
        try:
            kospi_df = pd.DataFrame()
            for _ in range(3):
                try:
                    temp_df = yf.download("^KS11", period="4y", interval="1d", progress=False)
                    if not temp_df.empty:
                        kospi_df = temp_df
                        break
                except: time.sleep(1)

            if not kospi_df.empty:
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
                
                def color_val(val):
                    color = '#ef4444' if val < 0 else '#22c55e'
                    return f"color: {color}; font-weight: bold;"
                
                formatted_kr_df = kr_df.map(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)
                st.dataframe(formatted_kr_df.style.map(lambda x: color_val(float(str(x).replace('%', '')))), use_container_width=True, hide_index=True)
            else: 
                st.warning("야후 파이낸스 통신망 일시 지연. 새로고침을 눌러주세요.")
        except Exception as e: 
            st.error(f"데이터를 불러오는 중 오류 발생: {e}")
            
        st.markdown("#### 📊 코스피 (KOSPI) 최근 1년 흐름 (일봉 자체 캔들 차트)")
        try:
            kospi_daily = pd.DataFrame()
            for _ in range(3):
                try:
                    kospi_daily = yf.download("^KS11", period="1y", interval="1d", progress=False)
                    if not kospi_daily.empty: break
                except: time.sleep(1)

            if not kospi_daily.empty:
                if isinstance(kospi_daily.columns, pd.MultiIndex):
                    df_chart = pd.DataFrame({
                        'Open': kospi_daily['Open'].iloc[:, 0] if isinstance(kospi_daily['Open'], pd.DataFrame) else kospi_daily['Open'],
                        'High': kospi_daily['High'].iloc[:, 0] if isinstance(kospi_daily['High'], pd.DataFrame) else kospi_daily['High'],
                        'Low':  kospi_daily['Low'].iloc[:, 0]  if isinstance(kospi_daily['Low'], pd.DataFrame)  else kospi_daily['Low'],
                        'Close':kospi_daily['Close'].iloc[:, 0] if isinstance(kospi_daily['Close'], pd.DataFrame) else kospi_daily['Close']
                    })
                else:
                    df_chart = kospi_daily[['Open', 'High', 'Low', 'Close']].copy()

                df_chart = df_chart.dropna().reset_index()
                df_chart.columns = ['Date', 'Open', 'High', 'Low', 'Close']
                
                # 캔들 색상 조건 (트레이딩뷰 오리지널 컬러 적용)
                color_condition = alt.condition("datum.Open <= datum.Close", alt.value("#089981"), alt.value("#f23645"))
                
                base = alt.Chart(df_chart).encode(
                    x=alt.X('Date:T', 
                            title=None, 
                            axis=alt.Axis(
                                labelAngle=0, 
                                labelColor='#787b86',
                                tickCount=12,
                                grid=True,
                                gridColor='#e0e3eb',
                                gridDash=[2, 2],
                                domain=False,
                                ticks=False,
                                labelPadding=10,
                                # 1월이면 연도를, 아니면 월(M월)을 표시하는 트레이딩뷰 완벽 모사 로직
                                labelExpr="timeFormat(datum.value, '%m') == '01' ? timeFormat(datum.value, '%Y') : timeFormat(datum.value, '%-m월')"
                            ))
                )
                
                rule = base.mark_rule().encode(
                    y=alt.Y('Low:Q', 
                            title=None, # '지수 (Point)' 글자 삭제
                            scale=alt.Scale(zero=False, padding=15), 
                            axis=alt.Axis(
                                orient='right', # 오른쪽 배치
                                labelColor='#787b86',
                                grid=True,
                                gridColor='#e0e3eb',
                                domain=False,
                                ticks=False,
                                format=','
                            )),
                    y2='High:Q',
                    color=color_condition
                )
                
                # 일봉에 맞게 캔들(바) 두께 최적화
                bar = base.mark_bar(size=3.0).encode(
                    y='Open:Q',
                    y2='Close:Q',
                    color=color_condition
                )
                
                candlestick_chart = (rule + bar).properties(height=350)
                
                # 테두리 제거 및 폰트 설정으로 트레이딩뷰 스타일 완벽 모사
                candlestick_chart = candlestick_chart.configure_view(
                    strokeWidth=0
                ).configure_axis(
                    labelFontSize=11,
                    titleFontSize=12
                )

                st.altair_chart(candlestick_chart, use_container_width=True)
                
            else:
                st.warning("야후 파이낸스 통신망 지연으로 차트를 불러오지 못했습니다. (새로고침을 눌러주세요)")
        except Exception as e:
            st.error(f"차트 데이터 오류 발생: {e}")
            
        st.markdown("---")

        yf_symbols = st.session_state.kospi100_state_df['YF_Symbol'].tolist()
        ui_symbols = st.session_state.kospi100_state_df['Symbol'].tolist()
        chunks_yf = [yf_symbols[i:i+25] for i in range(0, 100, 25)]
        chunks_ui = [ui_symbols[i:i+25] for i in range(0, 100, 25)]
        labels_kr = ["1위~25위", "26위~50위", "51위~75위", "76위~100위"]
        
        st.caption("야후 파이낸스 데이터 차단(Rate Limit)을 방지하기 위해 25개 종목씩 나누어 '4시간봉 EMA 200 vs 1일봉 EMA 200' 크로스 현황을 정밀 스캔합니다.")
        cols_kr = st.columns(4)
        for i in range(4):
            if i < len(chunks_yf):
                if cols_kr[i].button(f"🚀 코스피 {labels_kr[i]} 스캔", use_container_width=True, key=f"btn_kr_{i}"):
                    with st.spinner(f"코스피 {labels_kr[i]} 실시간 데이터 스캔 중... (IP 차단 방어 모드)"):
                        try:
                            data_1d_raw = yf.download(chunks_yf[i], period="2y", interval="1d", progress=False)
                            data_1h_raw = yf.download(chunks_yf[i], period="730d", interval="1h", progress=False)
                            
                            if 'Close' in data_1d_raw: data_1d = data_1d_raw['Close']
                            else: data_1d = data_1d_raw
                            if 'Close' in data_1h_raw: data_1h = data_1h_raw['Close']
                            else: data_1h = data_1h_raw
                            if isinstance(data_1d, pd.Series): data_1d = data_1d.to_frame(name=chunks_yf[i][0])
                            if isinstance(data_1h, pd.Series): data_1h = data_1h.to_frame(name=chunks_yf[i][0])
                            current_update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            
                            for j, yf_sym in enumerate(chunks_yf[i]):
                                ui_sym = chunks_ui[i][j]
                                if yf_sym not in data_1d.columns or yf_sym not in data_1h.columns: 
                                    c_type, c_date, c_price = "데이터 부족", "-", "-"
                                else:
                                    df_sym_1d = data_1d[yf_sym].dropna()
                                    df_sym_1h = data_1h[yf_sym].dropna()
                                    if len(df_sym_1d) < 150 or len(df_sym_1h) < 150: 
                                        c_type, c_date, c_price = "상장기간 부족", "-", "-"
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
                                            c_price = f"₩{merged.loc[latest_idx, 'Close']:,.0f}"
                                        else:
                                            c_type, c_date, c_price = "최근 1년 내 크로스 없음", "-", "-"
                                
                                mask = st.session_state.kospi100_state_df['Symbol'] == ui_sym
                                st.session_state.kospi100_state_df.loc[mask, '크로스 상태 (4H/1D EMA200)'] = c_type
                                st.session_state.kospi100_state_df.loc[mask, '크로스 날짜'] = c_date
                                st.session_state.kospi100_state_df.loc[mask, '크로스 당시 주가'] = c_price
                                st.session_state.kospi100_state_df.loc[mask, '업데이트 날짜'] = current_update_time

                            st.success(f"✅ {current_update_time} 기준, 코스피 {labels_kr[i]} 크로스 분석 완료!")
                            st.rerun() 
                        except Exception as e:
                            st.error(f"야후 파이낸스 스캔 중 오류 발생 (잠시 후 다시 시도해주세요): {str(e)}")

        display_cols_kr = ['순위', '시총', 'Symbol', 'Name', '산업군(Industry)', '분야 순위', '크로스 상태 (4H/1D EMA200)', '크로스 날짜', '크로스 당시 주가', '업데이트 날짜']
        st.dataframe(st.session_state.kospi100_state_df[display_cols_kr], use_container_width=True, hide_index=True, height=1100)
