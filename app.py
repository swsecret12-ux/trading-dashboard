# ... existing code ...
                                        ocr_mapping[num] = edited_ocr
                                        update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                        st.rerun()

with tab6:
    st.header("🏢 섹터 & 주도주 맵 (AI 리서치 저장소)")
    st.info("야후 파이낸스(yfinance)를 통해 4H/1D 이평선 크로스, 실적, 최신 뉴스를 긁어오고 AI가 심층 리포트를 작성합니다.")
    
    # 💡 두 개의 하위 탭으로 분리
    sub_tab_research, sub_tab_top100 = st.tabs(["🏢 내 종목 리서치", "🇺🇸 미국 시총 Top 100 맵"])
    
    with sub_tab_research:
        with st.expander("➕ 새 종목 리서치 자동화 추가하기"):
            with st.form("new_sector_stock"):
                c1, c2 = st.columns(2)
                s_ticker = c1.text_input("야후 파이낸스 티커 (예: NVDA, AAPL, SNOW)")
                s_sector = c2.selectbox("섹터 분류", ["AI", "소프트웨어", "반도체", "조선", "헬스케어", "코인", "기타"])
                
                s_issue = st.text_area("🔥 내가 주목하는 핵심 이슈 (나만의 투자 관점)", height=100)
                
                if st.form_submit_button("🤖 금융 데이터 자동 긁어오기 & AI 리서치 시작", type="primary"):
                    if s_ticker:
                        st_id = "swsecret@naver.com"
                        st_pw = "1!REre4423"
                        
                        with st.spinner("데이터 수집 및 크로스체크 심층 분석 중... (매크로 환경 분석으로 인해 1~2분 소요됩니다)"):
                            fin_data = fetch_financial_data(s_ticker.strip())
                            st_news_content = fetch_saveticker_news(st_id, st_pw)
                            
                            if "error" in fin_data: st.error(f"데이터 수집 실패: {fin_data['error']}")
                            else:
                                ai_res = analyze_sector_with_ai(s_ticker, s_sector, fin_data, s_issue, st_news_content)
                                
                                left_column_html = f"""
                                <div class='info-card'><h4>📉 이평선 분석 (4H vs 1D EMA 200)</h4>{fin_data.get('ma_html', '')}</div>
                                <div class='info-card'><h4>📊 가격 및 거래량 모멘텀</h4>{fin_data.get('momentum_html', '')}</div>
                                <div class='info-card'><h4>💰 분기 실적 (Earnings)</h4>{fin_data.get('earnings_html', '')}</div>
                                <div class='info-card'><h4>🔥 나의 투자 관점</h4><p>{s_issue}</p></div>
                                """
                                
                                insert_db("sector_analysis", {
                                    "ticker": s_ticker.upper(), "sector": s_sector, "market_cap": fin_data.get('market_cap', ''),
                                    "vol_1d": fin_data.get('last_cross_type', '-'), "vol_1w": fin_data.get('last_cross_date', '-'), 
                                    "vol_1m": "", "vol_1q": "", "vol_1y": "",
                                    "issue": left_column_html, "detail_data": fin_data.get('raw_news', ''), "ai_analysis": ai_res
                                })
                                st.success("리서치 리포트 등록 완료!"); time.sleep(1); st.rerun()

        df_sector = load_sector_data()
        if not df_sector.empty:
            filter_sec = st.selectbox("섹터 필터링", ["전체"] + list(df_sector['sector'].unique()))
            if filter_sec != "전체": df_sector = df_sector[df_sector['sector'] == filter_sec]
                
            disp_cols = ["ticker", "sector", "market_cap", "vol_1d", "vol_1w"]
            df_selected = st.dataframe(
                df_sector[disp_cols],
                column_config={
                    "ticker": "티커", "sector": "섹터", "market_cap": "시가총액",
                    "vol_1d": "EMA 크로스 (4H/1D)", "vol_1w": "크로스 발생일"
                },
                use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
            )
            
            if df_selected.get('selection', {}).get('rows', []):
                st.divider()
                stock_data = df_sector.iloc[df_selected['selection']['rows'][0]]
                s_id = stock_data['id']
                
                col_st1, col_st2 = st.columns([8, 2])
                with col_st1:
                    st.markdown(f"## 🏢 {stock_data['ticker']} 심층 리서치 리포트")
                    st.caption(f"섹터: {stock_data['sector']} | 시총: {stock_data['market_cap']}")
                with col_st2:
                    if st.button("🗑️ 삭제", type="primary", use_container_width=True): delete_db("sector_analysis", "id", s_id); st.rerun()
                
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
                  "studies": ["MAExp@tv-basicstudies", "MAExp@tv-basicstudies"],
                  "container_id": "tradingview_{stock_data['ticker']}"
                  }});
                  </script>
                </div>
                """
                components.html(tv_widget, height=650)
                st.caption("💡 팁: 차트 상단 톱니바퀴 또는 '지표' 버튼을 눌러 지수이동평균선(EMA) 2개의 길이를 각각 200으로 설정하세요! (1일봉, 4시간봉 번갈아가며 확인)")
                
                st.markdown("---")
                c_left, c_right = st.columns([4, 6], gap="large")
                with c_left:
                    st.markdown(stock_data['issue'], unsafe_allow_html=True)
                    with st.expander("📰 구글 기반 글로벌 핵심 뉴스 (파트너십, 실적 등)", expanded=False):
                        st.write(stock_data.get('detail_data', '수집된 뉴스가 없습니다.'))
                with c_right:
                    if stock_data.get('ai_analysis'):
                        st.markdown("#### 🤖 AI 월스트리트 애널리스트 심층 리포트")
                        st.markdown(stock_data['ai_analysis'], unsafe_allow_html=True)

    with sub_tab_top100:
        st.markdown("### 🇺🇸 미국 시총 상위 Top 100 기업 (S&P 100)")
        st.caption("미국을 이끄는 핵심 100대 기업의 티커와 섹터 정보입니다. 이 표를 기반으로 다음 자동화 기능을 연계할 수 있습니다.")
        
        @st.cache_data(ttl=86400)
        def get_sp100_data():
            try:
                res = requests.get('https://en.wikipedia.org/wiki/S%26P_100', headers={"User-Agent": "Mozilla/5.0"})
                tables = pd.read_html(io.StringIO(res.text))
                for df in tables:
                    if 'Symbol' in df.columns and 'Sector' in df.columns:
                        return df[['Symbol', 'Name', 'Sector']]
                return pd.DataFrame()
            except Exception as e:
                return pd.DataFrame({"Error": [str(e)]})
                
        df_sp100 = get_sp100_data()
        if not df_sp100.empty:
            sectors = ["전체"] + sorted(df_sp100['Sector'].dropna().unique().tolist())
            sel_sector = st.selectbox("섹터 필터링 (Top 100)", sectors)
            
            if sel_sector != "전체":
                df_display = df_sp100[df_sp100['Sector'] == sel_sector]
            else:
                df_display = df_sp100
                
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.error("Top 100 데이터를 불러오는 중 오류가 발생했습니다.")
