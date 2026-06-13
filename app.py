# ... existing code ...
import time
import json
import io
from PIL import Image
import streamlit.components.v1 as components # 💡 트레이딩뷰 위젯을 띄우기 위한 임포트 추가

# Import 에러를 막기 위해 백슬래시(\)를 사용하여 안전하게 한 줄씩 로드합니다.
# ... existing code ...
```

맨 아래 스크롤을 내려 **Tab 6 (섹터 & 주도주 리서치 맵)** 영역 전체를 아래 코드로 교체해 주세요.

```python:Main App:app.py
# ... existing code ...
# ==============================
# --- Tab 6: 🏢 섹터 & 주도주 리서치 맵 ---
# ==============================
with tab6:
    st.header("🏢 섹터 & 주도주 맵 (AI 리서치 저장소)")
    st.info("야후 파이낸스(yfinance)를 통해 종목의 시가총액, 변동성, 최신 뉴스를 긁어와 AI가 심층 리포트를 작성합니다.")
    
    with st.expander("➕ 새 종목 리서치 자동화 추가하기"):
        with st.form("new_sector_stock"):
            c1, c2 = st.columns(2)
            s_ticker = c1.text_input("야후 파이낸스 티커 (예: NVDA, AAPL, BTC-USD)")
            s_sector = c2.selectbox("섹터 분류", ["AI", "소프트웨어", "반도체", "조선", "헬스케어", "코인", "기타"]) # 💡 소프트웨어 추가
            s_issue = st.text_area("🔥 내가 주목하는 핵심 이슈")
            
            if st.form_submit_button("🤖 금융 데이터 긁어오기 & AI 리서치 시작", type="primary"):
                if s_ticker:
                    with st.spinner("데이터 수집 및 분석 중..."):
                        fin_data = fetch_financial_data(s_ticker.strip())
                        if "error" in fin_data: st.error(f"데이터 수집 실패: {fin_data['error']}")
                        else:
                            ai_res = analyze_sector_with_ai(s_ticker, s_sector, fin_data, s_issue)
                            
                            # 💡 기존 DB 스키마를 깨지 않으면서 현재가와 이평선 상태를 issue 컬럼에 예쁘게 포장해 저장합니다.
                            enriched_issue = f"**[현재가: ${fin_data['current_price']:.2f} / {fin_data['ma_status']}]**\n\n{s_issue}"
                            
                            insert_db("sector_analysis", {
                                "ticker": s_ticker.upper(), "sector": s_sector, "market_cap": fin_data['market_cap'],
                                "vol_1d": fin_data['vol_1d'], "vol_1w": fin_data['vol_1w'], "vol_1m": fin_data['vol_1m'], 
                                "vol_1q": fin_data['vol_1q'], "vol_1y": fin_data['vol_1y'],
                                "issue": enriched_issue, "detail_data": fin_data['raw_news'], "ai_analysis": ai_res
                            })
                            st.success("리서치 리포트 등록 완료!"); time.sleep(1); st.rerun()

    df_sector = load_sector_data()
    if not df_sector.empty:
        filter_sec = st.selectbox("섹터 필터링", ["전체"] + list(df_sector['sector'].unique()))
        if filter_sec != "전체": df_sector = df_sector[df_sector['sector'] == filter_sec]
            
        disp_cols = ["ticker", "sector", "market_cap", "vol_1d", "vol_1m", "vol_1y"]
        sel_stock = st.dataframe(df_sector[disp_cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        
        if sel_stock.get('selection', {}).get('rows', []):
            st.divider()
            stock_data = df_sector.iloc[sel_stock['selection']['rows'][0]]
            s_id = stock_data['id']
            s_ticker_val = stock_data['ticker']
            
            col_st1, col_st2 = st.columns([8, 2])
            with col_st1:
                st.markdown(f"## 🏢 {s_ticker_val} 리서치 리포트")
                st.caption(f"섹터: {stock_data['sector']} | 시총: {stock_data['market_cap']}")
            with col_st2:
                if st.button("🗑️ 삭제", type="primary", use_container_width=True): delete_db("sector_analysis", "id", s_id); st.rerun()
            
            # 💡 실시간 트레이딩뷰 위젯 삽입 (인터랙티브 차트)
            st.markdown(f"#### 📈 {s_ticker_val} 실시간 차트 (TradingView)")
            tv_widget = f"""
            <!-- TradingView Widget BEGIN -->
            <div class="tradingview-widget-container" style="height:450px;width:100%; margin-bottom: 20px;">
              <div id="tradingview_{s_ticker_val}" style="height:calc(100% - 32px);width:100%"></div>
              <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
              <script type="text/javascript">
              new TradingView.widget(
              {{
              "autosize": true,
              "symbol": "{s_ticker_val}",
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
              "container_id": "tradingview_{s_ticker_val}"
            }}
              );
              </script>
            </div>
            <!-- TradingView Widget END -->
            """
            components.html(tv_widget, height=450)

            st.markdown("#### 📊 최근 주가 변동성(수익률)")
            v1, v2, v3, v4, v5 = st.columns(5)
            v1.metric("1일", f"{stock_data['vol_1d']}%")
            v2.metric("1주일", f"{stock_data['vol_1w']}%")
            v3.metric("1개월", f"{stock_data['vol_1m']}%")
            v4.metric("1분기", f"{stock_data['vol_1q']}%")
            v5.metric("1년", f"{stock_data['vol_1y']}%")
            
            st.markdown("---")
            c_left, c_right = st.columns([4, 6], gap="large")
            with c_left:
                st.info(f"**🔥 나의 메모 및 가격 동향:**\n\n{stock_data['issue']}")
                with st.expander("📰 AI가 읽어본 야후 파이낸스 원문 뉴스", expanded=False):
                    st.write(stock_data.get('detail_data', '수집된 뉴스가 없습니다.'))
            with c_right:
                if stock_data.get('ai_analysis'):
                    st.markdown("#### 🤖 AI 월스트리트 애널리스트 분석")
                    # AI 결과를 Markdown으로 예쁘게 렌더링
                    st.markdown(stock_data['ai_analysis'], unsafe_allow_html=True)
