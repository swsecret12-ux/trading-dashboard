import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone
import yfinance as yf
import streamlit.components.v1 as components

def format_usd(usd_val):
    try:
        val = float(usd_val)
        if val <= 0: return "-"
        if val >= 1e9: return f"${val/1e9:.2f}B"
        elif val >= 1e6: return f"${val/1e6:.2f}M"
        return f"${val:,.0f}"
    except:
        return usd_val

def color_pct(val):
    if isinstance(val, str) and '%' in val:
        try:
            num = float(val.replace('%', '').replace('+', ''))
            color = '#ef4444' if num < 0 else '#22c55e'
            return f'color: {color}; font-weight: bold;'
        except: pass
    return ''

def render_crypto_map_tab():
    if "crypto100_state_df" not in st.session_state:
        st.session_state.crypto100_state_df = pd.DataFrame()

    st.markdown("### 🪙 글로벌 암호화폐 Top 100 맵 (실시간 데이터 기준)")
    st.info("💡 **알림:** 실시간 트레이딩뷰 서버에서 스테이블 코인을 제외한 순수 알트코인 시가총액 최상위 100개 명단을 즉시 스캔합니다.")

    if st.button("🔄 실시간 암호화폐 Top 100 스캔 시작", type="primary", key="btn_crypto_scan"):
        with st.spinner("글로벌 코인 마켓을 스캔하여 실시간 시총 100위를 선별 중입니다... (약 2초 소요)"):
            try:
                url = "https://scanner.tradingview.com/crypto/scan"
                payload = {
                    "filter": [
                        {"left": "market_cap_calc", "operation": "nempty"}
                    ],
                    "options": {"lang": "ko"},
                    "markets": ["crypto"],
                    "columns": ["name", "description", "market_cap_calc", "close", "change", "Perf.W", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y", "RSI"],
                    "sort": {"sortBy": "market_cap_calc", "sortOrder": "desc"},
                    "range": [0, 200] 
                }
                res = requests.post(url, json=payload, headers={"User-Agent": "Mozilla/5.0"})
                data = res.json()
                
                df_list = []
                seen_tickers = set()
                # 💡 가치 변동이 없는 스테이블 코인은 순위에서 과감히 제외합니다.
                stablecoins = ["USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDD", "USDP"]
                
                for item in data.get('data', []):
                    if len(df_list) >= 100: break
                    sym = item['d'][0] 
                    name_raw = item['d'][1]
                    mcap = item['d'][2]
                    close_p = item['d'][3]
                    chg_1d = item['d'][4]
                    chg_1w = item['d'][5]
                    chg_1m = item['d'][6]
                    chg_3m = item['d'][7]
                    chg_6m = item['d'][8]
                    chg_1y = item['d'][9]
                    rsi_val = item['d'][10]
                    
                    # 'BINANCE:BTCUSDT' 형태에서 'BTC'만 추출
                    base_ticker = sym.split(':')[-1].replace('USDT', '').replace('USD', '')
                    if not base_ticker: base_ticker = sym.split(':')[-1]
                    
                    if base_ticker in stablecoins: continue
                    if base_ticker in seen_tickers: continue
                    seen_tickers.add(base_ticker)
                    
                    yf_ticker = f"{base_ticker}-USD"
                    
                    df_list.append({
                        '순위': len(df_list) + 1,
                        '시총': format_usd(mcap),
                        'Symbol': base_ticker,
                        'YF_Symbol': yf_ticker,
                        'Name': name_raw,
                        '현재가': f"${close_p:,.4f}" if close_p else "-",
                        'RSI': f"🚨 {rsi_val:.1f}" if rsi_val and rsi_val < 30 else (f"{rsi_val:.1f}" if rsi_val else "-"),
                        '1일 변동': f"{chg_1d:+.2f}%" if chg_1d else "-",
                        '7일 변동': f"{chg_1w:+.2f}%" if chg_1w else "-",
                        '30일 변동': f"{chg_1m:+.2f}%" if chg_1m else "-",
                        '60일 변동': f"{chg_3m:+.2f}%" if chg_3m else "-",
                        '120일 변동': f"{chg_6m:+.2f}%" if chg_6m else "-",
                        '200일 변동': f"{chg_1y:+.2f}%" if chg_1y else "-",
                        '크로스 상태 (4H/1D EMA200)': "대기 중",
                        '크로스 날짜': "-",
                        '크로스 당시 주가': "-",
                        '업데이트 날짜': "-"
                    })
                
                st.session_state.crypto100_state_df = pd.DataFrame(df_list)
                st.success("✅ 스테이블 코인 제외, 순수 암호화폐 Top 100 리스트 업데이트 완료!")
            except Exception as e:
                st.error(f"데이터 스캔 중 오류가 발생했습니다: {e}")

    if not st.session_state.crypto100_state_df.empty:
        st.markdown("#### 📈 비트코인(BTC) 기간별 수익률 지표")
        try:
            btc_df = yf.download("BTC-USD", period="4y", interval="1d", progress=False)
            if not btc_df.empty:
                if isinstance(btc_df.columns, pd.MultiIndex): 
                    close_series = btc_df['Close'].iloc[:, 0].dropna()
                else: 
                    close_series = btc_df['Close'].dropna()
                
                curr = close_series.iloc[-1]
                def ret(days):
                    if len(close_series) > days: return float((curr - close_series.iloc[-(days+1)]) / close_series.iloc[-(days+1)] * 100)
                    return 0.0
                
                btc_data = {"1일": ret(1), "7일": ret(5), "1개월": ret(21), "3개월": ret(63), "6개월": ret(126), "1년": ret(365), "3년": ret(1095)}
                kr_df = pd.DataFrame([btc_data])
                
                def color_val(val):
                    color = '#ef4444' if val < 0 else '#22c55e'
                    return f"color: {color}; font-weight: bold;"
                
                formatted_kr_df = kr_df.map(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)
                st.dataframe(formatted_kr_df.style.map(lambda x: color_val(float(str(x).replace('%', '')))), use_container_width=True, hide_index=True)
        except Exception as e: 
            st.error(f"데이터를 불러오는 중 오류 발생: {e}")
            
        st.markdown("#### 📊 비트코인 (BTC/USDT) 실시간 흐름 (트레이딩뷰 공식 위젯)")
        tv_widget_crypto = """
        <div class="tradingview-widget-container" style="height:750px;width:100%; margin-bottom: 20px;">
          <div id="tradingview_crypto" style="height:calc(100% - 32px);width:100%"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({
          "autosize": true,
          "symbol": "BINANCE:BTCUSDT",
          "interval": "D",
          "timezone": "Etc/UTC",
          "theme": "light",
          "style": "1",
          "locale": "kr",
          "enable_publishing": false,
          "backgroundColor": "rgba(255, 255, 255, 1)",
          "gridColor": "rgba(240, 243, 250, 0)",
          "hide_top_toolbar": false,
          "hide_legend": false,
          "save_image": false,
          "container_id": "tradingview_crypto",
          "studies": [
            "RSI@tv-basicstudies",
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 200}}
          ]
          });
          </script>
        </div>
        """
        components.html(tv_widget_crypto, height=750)
            
        st.markdown("---")

        yf_symbols = st.session_state.crypto100_state_df['YF_Symbol'].tolist()
        ui_symbols = st.session_state.crypto100_state_df['Symbol'].tolist()
        chunks_yf = [yf_symbols[i:i+25] for i in range(0, 100, 25)]
        chunks_ui = [ui_symbols[i:i+25] for i in range(0, 100, 25)]
        labels_crypto = ["1위~25위", "26위~50위", "51위~75위", "76위~100위"]
        
        st.caption("야후 파이낸스 데이터 차단(Rate Limit)을 방지하기 위해 25개 종목씩 나누어 '4시간봉 EMA 200 vs 1일봉 EMA 200' 크로스 현황을 정밀 스캔합니다.")
        cols_crypto = st.columns(4)
        for i in range(4):
            if i < len(chunks_yf):
                if cols_crypto[i].button(f"🚀 암호화폐 {labels_crypto[i]} 스캔", use_container_width=True, key=f"btn_crypto_{i}"):
                    with st.spinner(f"암호화폐 {labels_crypto[i]} 실시간 데이터 스캔 중..."):
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
                                            c_price = f"${merged.loc[latest_idx, 'Close']:.4f}"
                                        else:
                                            c_type, c_date, c_price = "최근 1년 내 크로스 없음", "-", "-"
                                
                                mask = st.session_state.crypto100_state_df['Symbol'] == ui_sym
                                st.session_state.crypto100_state_df.loc[mask, '크로스 상태 (4H/1D EMA200)'] = c_type
                                st.session_state.crypto100_state_df.loc[mask, '크로스 날짜'] = c_date
                                st.session_state.crypto100_state_df.loc[mask, '크로스 당시 주가'] = c_price
                                st.session_state.crypto100_state_df.loc[mask, '업데이트 날짜'] = current_update_time

                            st.success(f"✅ {current_update_time} 기준, 암호화폐 {labels_crypto[i]} 크로스 분석 완료!")
                            st.rerun() 
                        except Exception as e:
                            st.error(f"스캔 중 오류 발생 (잠시 후 다시 시도해주세요): {str(e)}")

        display_cols = ['순위', '시총', 'Symbol', 'Name', '현재가', 'RSI', '1일 변동', '7일 변동', '30일 변동', '60일 변동', '120일 변동', '200일 변동', '크로스 상태 (4H/1D EMA200)', '크로스 날짜', '크로스 당시 주가', '업데이트 날짜']
        st.dataframe(st.session_state.crypto100_state_df[display_cols].style.map(color_pct, subset=['1일 변동', '7일 변동', '30일 변동', '60일 변동', '120일 변동', '200일 변동']), use_container_width=True, hide_index=True, height=1100)
