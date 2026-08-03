import streamlit as st
import pandas as pd
import time
import requests
import xml.etree.ElementTree as ET
import yfinance as yf
import json
import streamlit.components.v1 as components
from api_utils import insert_db, delete_db, load_sector_data
from market_research import fetch_financial_data, analyze_sector_with_ai

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

def render_native_chart(ticker_only, is_korean):
    st.markdown(f"#### 📈 {ticker_only} 실시간 정밀 차트 (TradingView 엔진 탑재)")
    st.caption("💡 날짜 가시성을 극대화하고, 거래량 단위를 '만/억' 단위로 직관적으로 변경했습니다. 캔들/거래량/RSI를 한눈에 스캔하세요.")
    
    # 💡 유료 사용자를 위한 특급 솔루션: 진짜 트레이딩뷰 다이렉트 브릿지 버튼!
    tv_symbol = f"KRX:{ticker_only}" if is_korean else ticker_only
    tv_url = f"https://www.tradingview.com/chart/?symbol={tv_symbol}"
    st.link_button(f"🚀 내 유료 트레이딩뷰(Pro) 계정에서 [{ticker_only}] 정밀 차트 열기 (작도/지표 연동)", tv_url, type="primary", use_container_width=True)
    st.write("") 
    
    with st.spinner("초고화질 차트 렌더링 중..."):
        try:
            df_chart = pd.DataFrame()
            
            # 1. 데이터 수집 로직 (한국=네이버, 미국=야후)
            if is_korean:
                url = f"https://fchart.stock.naver.com/sise.nhn?symbol={ticker_only}&timeframe=day&count=365&requestType=0"
                res = requests.get(url, timeout=5)
                root = ET.fromstring(res.text)
                items = root.findall('.//item')
                data = []
                for item in items:
                    row = item.attrib['data'].split('|')
                    data.append({
                        'Date': f"{row[0][:4]}-{row[0][4:6]}-{row[0][6:8]}",
                        'Open': float(row[1]), 'High': float(row[2]), 'Low': float(row[3]), 'Close': float(row[4]), 'Volume': float(row[5])
                    })
                if data: df_chart = pd.DataFrame(data)
            else:
                yf_data = yf.download(ticker_only, period="1y", interval="1d", progress=False)
                if not yf_data.empty:
                    if isinstance(yf_data.columns, pd.MultiIndex):
                        df_chart = pd.DataFrame({
                            'Open': yf_data['Open'].iloc[:, 0] if isinstance(yf_data['Open'], pd.DataFrame) else yf_data['Open'],
                            'High': yf_data['High'].iloc[:, 0] if isinstance(yf_data['High'], pd.DataFrame) else yf_data['High'],
                            'Low':  yf_data['Low'].iloc[:, 0]  if isinstance(yf_data['Low'], pd.DataFrame)  else yf_data['Low'],
                            'Close':yf_data['Close'].iloc[:, 0] if isinstance(yf_data['Close'], pd.DataFrame) else yf_data['Close'],
                            'Volume':yf_data['Volume'].iloc[:, 0] if isinstance(yf_data['Volume'], pd.DataFrame) else yf_data['Volume']
                        })
                    else:
                        df_chart = yf_data[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                    df_chart = df_chart.dropna().reset_index()
                    df_chart.rename(columns={df_chart.columns[0]: 'Date'}, inplace=True)
                    df_chart['Date'] = pd.to_datetime(df_chart['Date']).dt.strftime('%Y-%m-%d')
            
            if df_chart.empty:
                st.warning("차트 데이터를 불러오지 못했습니다. 종목 코드를 확인해주세요.")
                return

            # 2. RSI 계산 로직
            delta = df_chart['Close'].diff()
            gain = (delta.where(delta > 0, 0)).fillna(0)
            loss = (-delta.where(delta < 0, 0)).fillna(0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / avg_loss
            df_chart['RSI'] = 100 - (100 / (1 + rs))
            df_chart = df_chart.fillna(0) 

            # 3. 자바스크립트에 넘길 JSON 데이터 정제
            candle_data = [{"time": row['Date'], "open": row['Open'], "high": row['High'], "low": row['Low'], "close": row['Close']} for _, row in df_chart.iterrows()]
            volume_data = [{"time": row['Date'], "value": row['Volume'], "color": "rgba(8, 153, 129, 0.5)" if row['Close'] >= row['Open'] else "rgba(242, 54, 69, 0.5)"} for _, row in df_chart.iterrows()]
            rsi_data = [{"time": row['Date'], "value": row['RSI']} for _, row in df_chart.iterrows() if row['RSI'] > 0]
            
            json_candle = json.dumps(candle_data)
            json_volume = json.dumps(volume_data)
            json_rsi = json.dumps(rsi_data)

            # 4. 차트 UI 극대화 및 거래량 단위 한글 패치 (JS)
            html_code = f"""
            <div style="position: relative; width: 100%; height: 600px; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; background: white;">
                <!-- 💡 캔들을 가리지 않는 깔끔한 고정형 상단 패널 -->
                <div id="tv_legend" style="position: absolute; top: 12px; left: 16px; z-index: 10; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; pointer-events: none; background: rgba(255,255,255,0.92); padding: 12px 16px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e2e8f0;"></div>
                <div id="tv_chart" style="width: 100%; height: 100%;"></div>
            </div>
            <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
            <script>
                const chart = LightweightCharts.createChart(document.getElementById('tv_chart'), {{
                    layout: {{ textColor: '#333', background: {{ type: 'solid', color: '#ffffff' }} }},
                    grid: {{ vertLines: {{ color: '#f0f3fa' }}, horzLines: {{ color: '#f0f3fa' }} }},
                    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
                    timeScale: {{ borderColor: '#e0e3eb', timeVisible: false, fixLeftEdge: true, fixRightEdge: true }}
                }});

                chart.priceScale('right').applyOptions({{ scaleMargins: {{ top: 0.1, bottom: 0.25 }}, borderColor: '#e0e3eb' }});

                const candleSeries = chart.addCandlestickSeries({{
                    upColor: '#089981', downColor: '#f23645', borderVisible: false, wickUpColor: '#089981', wickDownColor: '#f23645'
                }});

                // 💡 거래량 차트 (가격 캔들 아래로 배치)
                const volumeSeries = chart.addHistogramSeries({{
                    color: '#26a69a', priceFormat: {{ type: 'volume' }}, priceScaleId: 'vol'
                }});
                chart.priceScale('vol').applyOptions({{ scaleMargins: {{ top: 0.75, bottom: 0.2 }}, visible: false }});

                // 💡 RSI 차트 (최하단 분리 배치)
                const rsiSeries = chart.addLineSeries({{ color: '#9c27b0', lineWidth: 2, priceScaleId: 'rsi' }});
                const rsiTop = chart.addLineSeries({{ color: '#a3a3a3', lineWidth: 1, lineStyle: 2, priceScaleId: 'rsi', lastValueVisible: false, priceLineVisible: false }});
                const rsiBot = chart.addLineSeries({{ color: '#a3a3a3', lineWidth: 1, lineStyle: 2, priceScaleId: 'rsi', lastValueVisible: false, priceLineVisible: false }});
                chart.priceScale('rsi').applyOptions({{ scaleMargins: {{ top: 0.85, bottom: 0 }}, borderColor: '#e0e3eb' }});

                const candleData = {json_candle};
                const volumeData = {json_volume};
                const rsiData = {json_rsi};

                candleSeries.setData(candleData);
                volumeSeries.setData(volumeData);
                rsiSeries.setData(rsiData);
                rsiTop.setData(rsiData.map(d => ({{time: d.time, value: 70}})));
                rsiBot.setData(rsiData.map(d => ({{time: d.time, value: 30}})));

                chart.timeScale().fitContent();

                // 💡 레전드(패널) 렌더링 및 거래량 단위 한글화 로직
                const legend = document.getElementById('tv_legend');
                const formatNum = (n) => new Intl.NumberFormat('ko-KR').format(n);
                const formatVol = (v) => {{
                    if(v >= 100000000) return (v / 100000000).toFixed(1) + '억';
                    if(v >= 10000) return (v / 10000).toFixed(0) + '만';
                    return formatNum(v);
                }};

                function updateLegend(param) {{
                    let cData, vData, rData;
                    if (param && param.time) {{
                        cData = param.seriesData.get(candleSeries);
                        vData = param.seriesData.get(volumeSeries);
                        rData = param.seriesData.get(rsiSeries);
                    }} else {{
                        cData = candleData[candleData.length - 1];
                        vData = volumeData[volumeData.length - 1];
                        rData = rsiData[rsiData.length - 1];
                    }}

                    if (cData) {{
                        const o = formatNum(cData.open), h = formatNum(cData.high), l = formatNum(cData.low), c = formatNum(cData.close);
                        const color = cData.close >= cData.open ? '#089981' : '#f23645';
                        const v = vData ? formatVol(vData.value) : '-';
                        const r = rData ? rData.value.toFixed(1) : '-';

                        legend.innerHTML = `
                            <div style="font-size: 18px; font-weight: bold; color: #191919; margin-bottom: 8px;">
                                {ticker_only} <span style="font-size: 14px; color: #787b86; font-weight: normal; margin-left: 6px;">${{cData.time}}</span>
                            </div>
                            <div style="display: flex; gap: 15px; font-size: 15px; margin-bottom: 8px;">
                                <div><span style="color:#787b86; margin-right:4px;">시가</span><strong style="color:${{color}}">${{o}}</strong></div>
                                <div><span style="color:#787b86; margin-right:4px;">고가</span><strong style="color:${{color}}">${{h}}</strong></div>
                                <div><span style="color:#787b86; margin-right:4px;">저가</span><strong style="color:${{color}}">${{l}}</strong></div>
                                <div><span style="color:#787b86; margin-right:4px;">종가</span><strong style="color:${{color}}">${{c}}</strong></div>
                            </div>
                            <div style="display: flex; gap: 20px; font-size: 14px; padding-top: 8px; border-top: 1px solid #e2e8f0;">
                                <div><span style="color:#787b86; margin-right:4px;">📊 거래량</span><strong style="color:#26a69a;">${{v}}</strong></div>
                                <div><span style="color:#787b86; margin-right:4px;">⚡ RSI(14)</span><strong style="color:#9c27b0;">${{r}}</strong></div>
                            </div>
                        `;
                    }}
                }}
                chart.subscribeCrosshairMove(updateLegend);
                updateLegend(null);
            </script>
            """
            components.html(html_code, height=620)
            
        except Exception as e:
            st.error(f"차트 렌더링 중 오류 발생: {e}")

def render_research_tab():
    with st.expander("➕ 새 종목 리서치 자동화 추가하기"):
        with st.form("new_sector_stock"):
            c1, c2 = st.columns(2)
            s_ticker = c1.text_input("야후 파이낸스 티커 (한국종목은 011200 또는 011200.KS 형태 입력)")
            s_sector = c2.selectbox("섹터 분류", ["AI", "소프트웨어", "반도체", "조선", "헬스케어", "금융", "기타"])
            s_issue = st.text_area("🔥 내가 주목하는 핵심 이슈 (나만의 투자 관점)", height=100)
            
            if st.form_submit_button("🤖 금융 데이터 자동 긁어오기 & AI 리서치 시작", type="primary"):
                clean_ticker = s_ticker.strip().upper()
                if clean_ticker:
                    with st.spinner("데이터 수집 및 크로스체크 심층 분석 중... (최대 10~20초)"):
                        try:
                            fin_data = fetch_financial_data(clean_ticker)
                            
                            if "error" in fin_data: 
                                st.error(f"데이터 수집 실패: {fin_data['error']}")
                            else:
                                company_name = fin_data.get('company_name', '')
                                ai_res = analyze_sector_with_ai(clean_ticker, company_name, s_sector, fin_data, s_issue, "별도 뉴스 생략")
                                
                                left_column_html = f"""
                                <div class='info-card'><h4>📉 이평선 분석 (4H vs 1D EMA 200)</h4>{fin_data.get('ma_html', '')}</div>
                                <div class='info-card'><h4>📊 가격 및 거래량 모멘텀</h4>{fin_data.get('momentum_html', '')}</div>
                                <div class='info-card'><h4>💰 분기 실적 (Earnings)</h4>{fin_data.get('earnings_html', '')}</div>
                                <div class='info-card'><h4>⚖️ 기업 가치 및 적정주가 (EPS × PER)</h4>{fin_data.get('valuation_html', '')}</div>
                                <div class='info-card'><h4>🔥 나의 투자 관점</h4><p>{s_issue}</p></div>
                                """
                                
                                safe_market_cap = float(fin_data.get('market_cap', 0)) if pd.notna(fin_data.get('market_cap', 0)) else 0.0
                                display_ticker = f"{clean_ticker} ({company_name})" if company_name else clean_ticker

                                res = insert_db("sector_analysis", {
                                    "ticker": display_ticker, 
                                    "sector": s_sector, "market_cap": safe_market_cap,
                                    "vol_1d": fin_data.get('last_cross_type', '-'), "vol_1w": fin_data.get('last_cross_date', '-'), 
                                    "vol_1m": "", "vol_1q": "", "vol_1y": "",
                                    "issue": left_column_html, "detail_data": fin_data.get('raw_news', ''), "ai_analysis": ai_res
                                })
                                
                                if res is not None and res.status_code in [200, 201]:
                                    st.success(f"✅ [{display_ticker}] 리서치 리포트 등록 완료! DB에 안전하게 저장되었습니다.")
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    err_msg = res.text if hasattr(res, 'text') else 'DB 응답 없음 (타임아웃 또는 연결 오류)'
                                    st.error(f"❌ DB 저장 실패! 에러 원인: {err_msg}")
                                    
                        except Exception as e:
                            st.error(f"분석 중 치명적 오류 발생: {str(e)}")

    df_sector = load_sector_data()
    if not df_sector.empty:
        filter_sec = st.selectbox("섹터 필터링", ["전체"] + list(df_sector['sector'].unique()))
        if filter_sec != "전체": df_sector = df_sector[df_sector['sector'] == filter_sec]
            
        df_display = df_sector.copy()
        df_display['market_cap_formatted'] = df_display['market_cap'].apply(lambda x: format_mcap_krw(float(x)) if pd.notna(x) and str(x).replace('.','',1).isdigit() else x)
        
        disp_cols = ["ticker", "sector", "market_cap_formatted", "vol_1d", "vol_1w"]
        
        df_selected = st.dataframe(
            df_display[disp_cols],
            column_config={
                "ticker": st.column_config.TextColumn("종목명(티커)", width="large"), 
                "sector": "섹터", 
                "market_cap_formatted": "시가총액", 
                "vol_1d": "EMA 크로스 (4H/1D)", 
                "vol_1w": "크로스 발생일"
            },
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row"
        )
        
        selected_rows = df_selected.get('selection', {}).get('rows', [])
        
        if selected_rows:
            st.markdown("---")
            col_title, col_btn = st.columns([8, 2])
            with col_title:
                st.markdown(f"### ⚙️ 선택 항목 관리 ({len(selected_rows)}개 선택됨)")
            with col_btn:
                if st.button("🗑️ 선택 항목 일괄 삭제", type="primary", use_container_width=True):
                    for idx in selected_rows:
                        row_id = df_display.iloc[idx]["id"]
                        delete_db("sector_analysis", "id", row_id)
                    st.rerun()

            if len(selected_rows) == 1:
                stock_data = df_display.iloc[selected_rows[0]]
                mcap_str = stock_data['market_cap_formatted']
                
                st.markdown("---")
                st.markdown(f"## 🏢 {stock_data['ticker']} 심층 리서치 리포트")
                st.caption(f"섹터: {stock_data['sector']} | 시총: {mcap_str}")
                
                raw_ticker = stock_data['ticker']
                ticker_only = raw_ticker.split(' ')[0].replace('.KS', '').replace('.KQ', '')
                
                # 💡 모든 종목(한국/미국)에 대해 가시성 100% Lightweight 차트 렌더링!
                render_native_chart(ticker_only, is_korean=ticker_only.isdigit())
                
                st.markdown("---")
                c_left, c_right = st.columns([4, 6], gap="large")
                with c_left:
                    st.markdown(stock_data['issue'], unsafe_allow_html=True)
                    with st.expander("📰 구글 기반 글로벌 핵심 뉴스 (출처 명확 표기)", expanded=False):
                        st.write(stock_data.get('detail_data', '수집된 뉴스가 없습니다.'))
                with c_right:
                    if stock_data.get('ai_analysis'):
                        st.markdown("#### 🤖 AI 월스트리트 애널리스트 심층 리포트 (비판적 시각 적용)")
                        st.markdown(stock_data['ai_analysis'], unsafe_allow_html=True)
            else:
                st.info("💡 하단의 상세 리포트와 차트를 보려면 표에서 **단 1개의 종목만** 체크해주세요.")
