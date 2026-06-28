import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone
import yfinance as yf
import streamlit.components.v1 as components

def format_usd_direct(usd_val):
    """달러(USD) 기준 시가총액을 보기 쉽게 포맷팅합니다."""
    try:
        val = float(usd_val)
        if val <= 0: return "-"
        if val >= 1e12: 
            return f"${val/1e12:.2f}T (조 달러)"
        elif val >= 1e9: 
            return f"${val/1e9:.2f}B (십억 달러)"
        elif val >= 1e6:
            return f"${val/1e6:.2f}M (백만 달러)"
        return f"${val:,.0f}"
    except:
        return usd_val

def color_pct(val):
    """등락률 %를 받아 색상을 입히는 함수"""
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

    st.markdown("### 🪙 글로벌 암호화폐 Top 100 맵 (실시간 자금 흐름)")
    st.info("💡 **알림:** 스테이블 코인(USDT 등), 랩핑 토큰(WBTC 등), 파생 롤오버(RL) 등을 모두 제거한 **순수 100대 메이저/알트코인** 명단입니다.")

    # 1. 상단 트레이딩뷰 위젯 (비트코인 대장주 기준)
    tv_widget_crypto = """
    <div class="tradingview-widget-container" style="height:600px;width:100%; margin-bottom:20px;">
      <div id="tradingview_crypto" style="height:100%;width:100%"></div>
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
      "container_id": "tradingview_crypto",
      "studies": [
        "RSI@tv-basicstudies",
        {"id": "MASimple@tv-basicstudies", "inputs": {"length": 200}}
      ]
      });
      </script>
    </div>
    """
    components.html(tv_widget_crypto, height=600)
    
    st.markdown("---")

    if st.button("🔄 실시간 순수 암호화폐 Top 100 스캔 시작", type="primary"):
        with st.spinner("잡코인 및 파생상품을 필터링하며 글로벌 시총 100위를 선별 중입니다..."):
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
                    "range": [0, 400] # 필터링으로 빠질 것을 대비해 넉넉하게 400개 스캔
                }
                res = requests.post(url, json=payload, headers={"User-Agent": "Mozilla/5.0"})
                data = res.json()
                
                df_list = []
                seen_tickers = set()
                
                # 💡 악성 파생/스테이블/랩핑 코인 초강력 필터링 리스트
                skip_exact = {
                    'USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'USDE', 'PYUSD', 'UST', 'UDC', # 스테이블 코인
                    'WBTC', 'WETH', 'STETH', 'WBNB', 'RETH', 'CBETH', 'WEETH', # 랩핑/스테이킹 코인
                    'C', 'S', 'RL', 'RAIN', 'HYPE' # 기타 쓰레기값 및 겹침
                }
                
                for item in data.get('data', []):
                    if len(df_list) >= 100: break
                    
                    sym = item['d'][0] # ex) BINANCE:BTCUSDT
                    name_raw = item['d'][1] # ex) Bitcoin / Dollar
                    mcap = item['d'][2]
                    close_p = item['d'][3]
                    chg_1d = item['d'][4]
                    chg_1w = item['d'][5]
                    chg_1m = item['d'][6]
                    chg_3m = item['d'][7]
                    chg_6m = item['d'][8]
                    chg_1y = item['d'][9]
                    rsi_val = item['d'][10]
                    
                    # 티커명 정제 (BTCUSDT -> BTC)
                    raw_ticker = sym.split(':')[-1]
                    clean_sym = raw_ticker.replace('USDT', '').replace('USDC', '').replace('USD', '').replace('EUR', '')
                    
                    if not clean_sym: continue
                    
                    # 💡 필터 1: 특정 블랙리스트 컷
                    if clean_sym in skip_exact: continue
                    
                    # 💡 필터 2: RL(롤오버), UP/DOWN(레버리지) 컷
                    if clean_sym.endswith('RL') or clean_sym.endswith('UP') or clean_sym.endswith('DOWN'): continue
                    if clean_sym.endswith('BULL') or clean_sym.endswith('BEAR'): continue
                    
                    # 💡 필터 3: 중복 컷 (이미 등록된 심볼이면 패스)
                    if clean_sym in seen_tickers: continue
                    seen_tickers.add(clean_sym)
                    
                    if rsi_val: rsi_str = f"🚨 {rsi_val:.1f}" if rsi_val < 25 else f"{rsi_val:.1f}"
                    else: rsi_str = "-"
                    
                    # 표시용 이름 정제 (Bitcoin / Dollar -> Bitcoin)
                    display_name = name_raw.split(" / ")[0].strip() if " / " in name_raw else name_raw
                    
                    df_list.append({
                        '순위': len(df_list) + 1,
                        'Symbol': clean_sym,
                        'Name': display_name,
                        '시총': format_usd_direct(mcap),
                        '현재가': f"${close_p:,.4f}" if close_p else "-",
                        'RSI': rsi_str,
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
                st.success("✅ 불순물 및 중복 코인 완벽 제거! 순수 글로벌 Top 100 코인 리스트 업데이트 완료!")
            except Exception as e:
                st.error(f"데이터 스캔 중 오류가 발생했습니다: {e}")

    if not st.session_state.crypto100_state_df.empty:
        
        ui_symbols = st.session_state.crypto100_state_df['Symbol'].tolist()
        chunks_ui = [ui_symbols[i:i+25] for i in range(0, 100, 25)]
        labels_cr = ["1위~25위", "26위~50위", "51위~75위", "76위~100위"]
        
        st.caption("야후 파이낸스 데이터 차단을 방지하기 위해 25개 종목씩 나누어 '4시간봉 vs 1일봉 EMA 200' 크로스 현황을 정밀 스캔합니다.")
        cols_cr = st.columns(4)
        
        for i in range(4):
            if i < len(chunks_ui):
                if cols_cr[i].button(f"🚀 암호화폐 {labels_cr[i]} 스캔", use_container_width=True, key=f"btn_cr_{i}"):
                    with st.spinner(f"Top {labels_cr[i]} 실시간 EMA 크로스 분석 중..."):
                        try:
                            # 💡 야후 파이낸스 크립토 티커 변환 규칙 (-USD 붙이기)
                            yf_symbols = [f"{sym}-USD" for sym in chunks_ui[i]]
                            
                            data_1d_raw = yf.download(yf_symbols, period="2y", interval="1d", progress=False)
                            data_1h_raw = yf.download(yf_symbols, period="730d", interval="1h", progress=False)
                            
                            if 'Close' in data_1d_raw: data_1d = data_1d_raw['Close']
                            else: data_1d = data_1d_raw
                            if 'Close' in data_1h_raw: data_1h = data_1h_raw['Close']
                            else: data_1h = data_1h_raw
                            
                            if isinstance(data_1d, pd.Series): data_1d = data_1d.to_frame(name=yf_symbols[0])
                            if isinstance(data_1h, pd.Series): data_1h = data_1h.to_frame(name=yf_symbols[0])
                            current_update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            
                            for j, sym in enumerate(chunks_ui[i]):
                                yf_sym = f"{sym}-USD"
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
                                            c_price = f"${merged.loc[latest_idx, 'Close']:,.4f}"
                                        else:
                                            c_type, c_date, c_price = "최근 1년 내 없음", "-", "-"
                                
                                mask = st.session_state.crypto100_state_df['Symbol'] == sym
                                st.session_state.crypto100_state_df.loc[mask, '크로스 상태 (4H/1D EMA200)'] = c_type
                                st.session_state.crypto100_state_df.loc[mask, '크로스 날짜'] = c_date
                                st.session_state.crypto100_state_df.loc[mask, '크로스 당시 주가'] = c_price
                                st.session_state.crypto100_state_df.loc[mask, '업데이트 날짜'] = current_update_time

                            st.success(f"✅ {current_update_time} 기준, 암호화폐 {labels_cr[i]} 크로스 분석 완료!")
                            st.rerun() 
                        except Exception as e:
                            st.error(f"야후 파이낸스 스캔 중 오류 발생: {str(e)}")

        display_cols_cr = [
            '순위', 'Symbol', 'Name', '시총', '현재가', 'RSI', 
            '1일 변동', '7일 변동', '30일 변동', '60일 변동', '120일 변동', '200일 변동', 
            '크로스 상태 (4H/1D EMA200)', '크로스 날짜', '크로스 당시 주가', '업데이트 날짜'
        ]

        st.dataframe(
            st.session_state.crypto100_state_df[display_cols_cr].style.map(color_pct, subset=['1일 변동', '7일 변동', '30일 변동', '60일 변동', '120일 변동', '200일 변동']),
            column_config={
                "순위": st.column_config.NumberColumn(width="small"),
                "Symbol": st.column_config.TextColumn("심볼", width="small"),
                "Name": st.column_config.TextColumn("이름", width="medium"),
                "시총": st.column_config.TextColumn("시총", width="small"),
                "현재가": st.column_config.TextColumn("현재가", width="small"),
                "RSI": st.column_config.TextColumn("RSI", width="small"),
                "1일 변동": st.column_config.TextColumn("1일", width="small"),
                "7일 변동": st.column_config.TextColumn("7일", width="small"),
                "30일 변동": st.column_config.TextColumn("30일", width="small"),
                "60일 변동": st.column_config.TextColumn("60일", width="small"),
                "120일 변동": st.column_config.TextColumn("120일", width="small"),
                "200일 변동": st.column_config.TextColumn("200일", width="small"),
                "크로스 상태 (4H/1D EMA200)": st.column_config.TextColumn("EMA크로스", width="medium"),
                "크로스 날짜": st.column_config.TextColumn("크로스날짜", width="small"),
                "크로스 당시 주가": st.column_config.TextColumn("크로스가", width="small"),
                "업데이트 날짜": st.column_config.TextColumn("업데이트", width="small")
            },
            use_container_width=True, 
            hide_index=True, 
            height=1100
        )
