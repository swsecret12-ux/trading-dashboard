import streamlit as st
import pandas as pd
import time
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

def render_research_tab():
    with st.expander("➕ 새 종목 리서치 자동화 추가하기"):
        with st.form("new_sector_stock"):
            c1, c2 = st.columns(2)
            s_ticker = c1.text_input("야후 파이낸스 티커 (한국종목은 005930 또는 005930.KS 형태 입력)")
            s_sector = c2.selectbox("섹터 분류", ["AI", "소프트웨어", "반도체", "조선", "헬스케어", "금융", "기타"])
            s_issue = st.text_area("🔥 내가 주목하는 핵심 이슈 (나만의 투자 관점)", height=100)
            
            if st.form_submit_button("🤖 금융 데이터 자동 긁어오기 & AI 리서치 시작", type="primary"):
                if s_ticker:
                    with st.spinner("데이터 수집 및 크로스체크 심층 분석 중... (최대 10초)"):
                        try:
                            fin_data = fetch_financial_data(s_ticker.strip())
                            st_news_content = "별도 뉴스 생략"
                            
                            if "error" in fin_data: 
                                st.error(f"데이터 수집 실패: {fin_data['error']}")
                            else:
                                ai_res = analyze_sector_with_ai(s_ticker, s_sector, fin_data, s_issue, st_news_content)
                                left_column_html = f"""
                                <div class='info-card'><h4>📉 이평선 분석 (4H vs 1D EMA 200)</h4>{fin_data.get('ma_html', '')}</div>
                                <div class='info-card'><h4>📊 가격 및 거래량 모멘텀</h4>{fin_data.get('momentum_html', '')}</div>
                                <div class='info-card'><h4>💰 분기 실적 (Earnings)</h4>{fin_data.get('earnings_html', '')}</div>
                                <div class='info-card'><h4>⚖️ 기업 가치 및 적정주가 (EPS × PER)</h4>{fin_data.get('valuation_html', '')}</div>
                                <div class='info-card'><h4>🔥 나의 투자 관점</h4><p>{s_issue}</p></div>
                                """
                                
                                # 💡 수정 1: market_cap 데이터를 float으로 강제 변환하여 JSON 에러(np.int64 튕김) 방지
                                safe_market_cap = float(fin_data.get('market_cap', 0)) if pd.notna(fin_data.get('market_cap', 0)) else 0.0

                                res = insert_db("sector_analysis", {
                                    "ticker": s_ticker.upper(), "sector": s_sector, "market_cap": safe_market_cap,
                                    "vol_1d": fin_data.get('last_cross_type', '-'), "vol_1w": fin_data.get('last_cross_date', '-'), 
                                    "vol_1m": "", "vol_1q": "", "vol_1y": "",
                                    "issue": left_column_html, "detail_data": fin_data.get('raw_news', ''), "ai_analysis": ai_res
                                })
                                
                                # 💡 수정 2: DB 저장이 완벽하게 성공(200 또는 201)했을 때만 화면 새로고침
                                if res is not None and res.status_code in [200, 201]:
                                    st.success("✅ 리서치 리포트 등록 완료! DB에 안전하게 저장되었습니다.")
                                    time.sleep(2) # 성공 문구를 읽을 수 있도록 2초 대기
                                    st.rerun()
                                else:
                                    # DB 저장이 실패하면 화면을 새로고침하지 않고 에러를 화면에 고정 표시
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
            column_config={"ticker": "티커", "sector": "섹터", "market_cap_formatted": "시가총액", "vol_1d": "EMA 크로스 (4H/1D)", "vol_1w": "크로스 발생일"},
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )
        
        if df_selected.get('selection', {}).get('rows', []):
            st.divider()
            stock_data = df_sector.iloc[df_selected['selection']['rows'][0]]
            s_id = stock_data['id']
            mcap_str = format_mcap_krw(float(stock_data['market_cap'])) if pd.notna(stock_data['market_cap']) and str(stock_data['market_cap']).replace('.','',1).isdigit() else stock_data['market_cap']
            
            col_st1, col_st2 = st.columns([8, 2])
            with col_st1:
                st.markdown(f"## 🏢 {stock_data['ticker']} 심층 리서치 리포트")
                st.caption(f"섹터: {stock_data['sector']} | 시총: {mcap_str}")
            with col_st2:
                if st.button("🗑️ 삭제", type="primary", use_container_width=True): 
                    delete_db("sector_analysis", "id", s_id)
                    st.rerun()
            
            st.markdown(f"#### 📈 {stock_data['ticker']} 실시간 차트 (TradingView)")
            tv_widget = f"""
            <div class="tradingview-widget-container" style="height:650px;width:100%; margin-bottom: 20px;">
              <div id="tradingview_{stock_data['ticker']}" style="height:calc(100% - 32px);width:100%"></div>
              <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
              <script type="text/javascript">
              new TradingView.widget({{
              "autosize": true, "symbol": "{stock_data['ticker']}", "interval": "D", "timezone": "Etc/UTC",
              "theme": "light", "style": "1", "locale": "kr", "enable_publishing": false,
              "backgroundColor": "rgba(255, 255, 255, 1)", "gridColor": "rgba(240, 243, 250, 0)",
              "hide_top_toolbar": false, "hide_legend": false, "save_image": false,
              "studies": ["MAExp@tv-basicstudies", "RSI@tv-basicstudies"],
              "container_id": "tradingview_{stock_data['ticker']}"
              }});
              </script>
            </div>
            """
            components.html(tv_widget, height=650)
            st.caption("💡 팁: 차트 상단 톱니바퀴 버튼을 눌러 EMA(지수이동평균)와 RSI의 설정을 입맛대로 변경하세요!")
            
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
