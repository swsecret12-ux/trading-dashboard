import streamlit as st
import pandas as pd
import time
import requests
import xml.etree.ElementTree as ET
import yfinance as yf
import altair as alt
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
    st.markdown(f"#### 📈 {ticker_only} 실시간 자체 렌더링 차트")
    st.caption("💡 대시보드 내에서는 딜레이나 끊김이 없는 자체 차트로 흐름을 빠르게 파악하세요.")
    
    # 💡 가독성 극대화를 위한 툴팁(Tooltip) 및 표면 CSS 강제 주입
    st.markdown("""
    <style>
    #vg-tooltip-element {
        font-size: 16px !important;
        font-family: 'Pretendard', 'Malgun Gothic', sans-serif !important;
        font-weight: 700 !important;
        color: #1e293b !important;
        background-color: rgba(255, 255, 255, 0.95) !important;
        border: 3px solid #3b82f6 !important;
        border-radius: 8px !important;
        padding: 12px 18px !important;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2) !important;
        z-index: 9999 !important;
    }
    #vg-tooltip-element td.key { 
        color: #64748b !important; 
        font-size: 15px !important; 
        padding-right: 15px !important;
    }
    #vg-tooltip-element td.value { 
        font-size: 18px !important; 
        color: #0f172a !important; 
        font-weight: 900 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 💡 유료 사용자를 위한 특급 솔루션: 진짜 트레이딩뷰 다이렉트 브릿지 버튼!
    tv_symbol = f"KRX:{ticker_only}" if is_korean else ticker_only
    tv_url = f"https://www.tradingview.com/chart/?symbol={tv_symbol}"
    st.link_button(f"🚀 내 유료 트레이딩뷰(Pro) 계정에서 [{ticker_only}] 정밀 차트 열기 (작도/지표 완벽 연동)", tv_url, type="primary", use_container_width=True)
    st.write("") # 간격 띄우기
    
    try:
        df_chart = pd.DataFrame()
        
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
                    'Open': float(row[1]),
                    'High': float(row[2]),
                    'Low': float(row[3]),
                    'Close': float(row[4]),
                    'Volume': float(row[5])
                })
            if data: 
                df_chart = pd.DataFrame(data)
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

        delta = df_chart['Close'].diff()
        gain = (delta.where(delta > 0, 0)).fillna(0)
        loss = (-delta.where(delta < 0, 0)).fillna(0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df_chart['RSI'] = 100 - (100 / (1 + rs))

        color_condition = alt.condition("datum.Open <= datum.Close", alt.value("#089981"), alt.value("#f23645"))
        min_price = df_chart['Low'].min() * 0.98
        max_price = df_chart['High'].max() * 1.02
        fmt_price = ',.0f' if is_korean else ',.2f'
        
        hover = alt.selection_point(fields=['Date'], nearest=True, on='mouseover', empty=False, clear='mouseout')
        
        x_axis_hidden = alt.X('Date:O', axis=alt.Axis(labels=False, ticks=False, domain=False, title=None))
        x_axis_show = alt.X('Date:O', title=None, axis=alt.Axis(
            labelAngle=0, labelColor='#787b86', 
            labelExpr="indexof(datum.label, datum.value) % 20 == 0 ? datum.value : ''", 
            grid=True, gridColor='#e0e3eb', gridDash=[2, 2], domain=False, ticks=False
        ))
        
        base = alt.Chart(df_chart)
        
        selectors = base.mark_point(size=100).encode(
            x=x_axis_hidden, opacity=alt.value(0),
            tooltip=[
                alt.Tooltip('Date:O', title='날짜'),
                alt.Tooltip('Open:Q', format=fmt_price, title='시가'),
                alt.Tooltip('High:Q', format=fmt_price, title='고가'),
                alt.Tooltip('Low:Q', format=fmt_price, title='저가'),
                alt.Tooltip('Close:Q', format=fmt_price, title='종가'),
                alt.Tooltip('Volume:Q', format=',.0f', title='거래량'),
                alt.Tooltip('RSI:Q', format='.2f', title='RSI(14)')
            ]
        ).add_params(hover)
        
        rules = base.mark_rule(color='#787b86', strokeWidth=1, strokeDash=[5,5]).encode(x=x_axis_hidden).transform_filter(hover)
        
        rule_candle = base.mark_rule(size=2.0).encode(
            x=x_axis_hidden,
            y=alt.Y('Low:Q', title=None, scale=alt.Scale(domain=[min_price, max_price]), axis=alt.Axis(orient='right', format=fmt_price, labelFontSize=12)),
            y2='High:Q',
            color=color_condition
        )
        bar_candle = base.mark_bar(size=5.0).encode(x=x_axis_hidden, y='Open:Q', y2='Close:Q', color=color_condition)
        candlestick = (rule_candle + bar_candle + selectors + rules).properties(height=450)
        
        volume_bar = base.mark_bar(size=5.0).encode(
            x=x_axis_hidden, 
            y=alt.Y('Volume:Q', title=None, axis=alt.Axis(orient='right', format='.2s', labelFontSize=12)), 
            color=color_condition
        )
        volume_chart = (volume_bar + selectors + rules).properties(height=100)
        
        rsi_line = base.mark_line(color='#673ab7', strokeWidth=2).encode(
            x=x_axis_show, 
            y=alt.Y('RSI:Q', title='RSI', scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(orient='right', labelFontSize=12))
        )
        rsi_baseline = alt.Chart(pd.DataFrame({'y': [30, 70]})).mark_rule(strokeDash=[5,5], color='gray').encode(y='y')
        rsi_chart = (rsi_line + rsi_baseline + selectors.encode(x=x_axis_show) + rules.encode(x=x_axis_show)).properties(height=100)
        
        # 💡 축(Axis) 글씨 크기 및 굵기 대폭 상향
        combined = alt.vconcat(candlestick, volume_chart, rsi_chart, spacing=0).resolve_scale(x='shared').configure_view(stroke='lightgray', strokeWidth=1).configure_axis(
            labelFontSize=13,
            titleFontSize=15,
            labelFontWeight='bold',
            labelColor='#1e293b'
        )
        st.altair_chart(combined, use_container_width=True)
        
    except Exception as e:
        st.error(f"차트 렌더링 중 치명적 오류 발생 (서버 확인 필요): {e}")

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
            
            # 다중 선택 삭제 로직
            col_title, col_btn = st.columns([8, 2])
            with col_title:
                st.markdown(f"### ⚙️ 선택 항목 관리 ({len(selected_rows)}개 선택됨)")
            with col_btn:
                if st.button("🗑️ 선택 항목 일괄 삭제", type="primary", use_container_width=True):
                    for idx in selected_rows:
                        row_id = df_display.iloc[idx]["id"]
                        delete_db("sector_analysis", "id", row_id)
                    st.rerun()

            # 단 1개만 선택했을 때 리포트 렌더링
            if len(selected_rows) == 1:
                stock_data = df_display.iloc[selected_rows[0]]
                mcap_str = stock_data['market_cap_formatted']
                
                st.markdown("---")
                st.markdown(f"## 🏢 {stock_data['ticker']} 심층 리서치 리포트")
                st.caption(f"섹터: {stock_data['sector']} | 시총: {mcap_str}")
                
                raw_ticker = stock_data['ticker']
                ticker_only = raw_ticker.split(' ')[0].replace('.KS', '').replace('.KQ', '')
                
                # 오류 제로의 파이썬 네이티브 차트 호출 (내부에는 유료계정 직행 버튼 포함)
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
