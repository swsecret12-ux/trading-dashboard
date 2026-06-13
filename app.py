import streamlit as st
import pandas as pd
from datetime import datetime
import time
import json
import io
from PIL import Image
import streamlit.components.v1 as components 

from api_utils import \
    insert_db, update_db, delete_db, upload_image_to_supabase, \
    load_trade_data, load_archive_data, get_recent_archive_context, \
    load_theory_db, get_gemini_keys, parse_ai_json, ask_gemini_dynamic, \
    get_real_ocr_text, get_real_ai_advice, render_ai_advice_block, \
    render_blog_image_html, render_crisp_image_html, get_file_group_info, \
    execute_survival_trade, load_sector_data

from market_research import fetch_financial_data, analyze_sector_with_ai, fetch_saveticker_news

st.set_page_config(page_title="나만의 트레이딩 대시보드", layout="wide")

st.markdown("""
<style>
div[data-testid="stInfo"] p { font-size: 1.1rem; } 
div[data-testid="stError"] p { font-size: 1.1rem; }
div[data-testid="stMetricValue"] { font-size: 1.2rem !important; }
div[data-testid="stMetricLabel"] { font-size: 0.85rem !important; color: #666; }

.info-card {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 20px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}
.info-card h4 {
    color: #1e40af;
    margin-top: 0;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 10px;
}
.ma-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 10px;
    font-size: 0.95rem;
}
.ma-table th, .ma-table td {
    border: 1px solid #cbd5e1;
    padding: 8px 12px;
    text-align: left;
}
.ma-table th {
    background-color: #e2e8f0;
    font-weight: bold;
    color: #333;
}
.ma-table tr:nth-child(even) {
    background-color: #f1f5f9;
}

@media (max-width: 768px) {
    .block-container { padding-top: 2rem !important; padding-left: 1rem !important; padding-right: 1rem !important; padding-bottom: 2rem !important; }
    h1 { font-size: 1.8rem !important; } h2 { font-size: 1.5rem !important; } h3 { font-size: 1.2rem !important; } p, span, div { font-size: 1rem !important; }
}
</style>
""", unsafe_allow_html=True)

st.title("📈 나만의 클라우드 매매 복기 & 자동 AI 분석 시스템")

if "ai_analysis_done" not in st.session_state: st.session_state.ai_analysis_done = False
if "ai_result" not in st.session_state: st.session_state.ai_result = ""
if "ai_view_text" not in st.session_state: st.session_state.ai_view_text = ""
if "ai_img_files" not in st.session_state: st.session_state.ai_img_files = [] 
if "uploader_key" not in st.session_state: st.session_state.uploader_key = 0 
if "t2_ticker" not in st.session_state: st.session_state.t2_ticker = ""

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📝 매매 기록 보관지", "🔎 AI 차트 & 관점 분석", "📚 기본 이론 & DB", "🤖 자동매매 사령실", "📁 분석 자료 아카이브", "🏢 섹터 & 주도주 맵"])

with tab1:
    st.header("📝 매매 기록 보관지")
    df_trade = load_trade_data()
    if not df_trade.empty: df_trade = df_trade.sort_values(by='date', ascending=False).reset_index(drop=True)
    
    with st.expander("➕ 새로운 매매 기록 추가하기", expanded=True):
        uploaded_images = st.file_uploader("차트 캡처 업로드", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key="trade_uploader")
        
        st.markdown("#### 📝 1. 기본 정보")
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns(4)
            with col1: date = st.date_input("날짜", datetime.today())
            with col2: ticker = st.text_input("종목명 (예: BTC)").upper()
            with col3: timeframe = st.selectbox("타임프레임", ["1m", "5m", "15m", "1H", "4H", "1D"])
            with col4: setup_pattern = st.text_input("셋업/패턴")
            
        st.markdown("#### 💰 2. 포지션 및 수익 계산")
        with st.container(border=True):
            col5, col6, col7, col8, col9 = st.columns(5)
            with col5: position = st.selectbox("포지션", ["Long", "Short"])
            with col6: leverage = st.number_input("레버리지 (x)", min_value=1, value=10, step=1)
            with col7: margin = st.number_input("투자 원금 ($)", min_value=0.0, value=1000.0, step=100.0)
            with col8: entry_price = st.number_input("진입 가격", min_value=0.0, value=0.0, format="%.4f")
            with col9: exit_price = st.number_input("종료 가격", min_value=0.0, value=0.0, format="%.4f")
            
            profit_calc = 0.0
            if entry_price > 0 and exit_price > 0:
                if position == "Long": profit_calc = ((exit_price - entry_price) / entry_price) * margin * leverage
                else: profit_calc = ((entry_price - exit_price) / entry_price) * margin * leverage
            
            auto_res = "무"
            if profit_calc > 0: auto_res = "승"
            elif profit_calc < 0: auto_res = "패"
            
            st.info(f"**💡 자동 계산된 수익금:** `${profit_calc:,.2f}` &nbsp;&nbsp;|&nbsp;&nbsp; **ROE (수익률):** `{profit_calc/margin*100 if margin>0 else 0:,.2f}%`")
            
        st.markdown("#### 📊 3. 결과 및 근거")
        with st.container(border=True):
            col10, col11 = st.columns(2)
            idx_res = ["승", "무", "패"].index(auto_res) if (entry_price > 0 and exit_price > 0) else 0
            with col10: result = st.selectbox("최종 결과", ["승", "무", "패"], index=idx_res)
            with col11: rr_ratio = st.text_input("손익비 (예: 1:2)")
            entry_basis = st.text_area("🟢 진입 근거", height=80)
            exit_basis = st.text_area("🔴 종료 근거", height=80)
            
        if st.button("☁️ 클라우드에 기록 저장", type="primary", use_container_width=True):
            if not ticker: st.error("종목명을 입력해주세요!")
            else:
                saved_urls = [u for u in [upload_image_to_supabase(img, "trade") for img in (uploaded_images or [])] if u]
                detailed_entry = f"[진입가: {entry_price} | 레버리지: {leverage}x | 원금: ${margin}]\n{entry_basis}"
                detailed_exit = f"[종료가: {exit_price}]\n{exit_basis}"
                
                insert_db("trade_history", {
                    "date": date.strftime("%Y-%m-%d"), "ticker": ticker, "timeframe": timeframe, "setup_pattern": setup_pattern, 
                    "position": position, "result": result, "rr_ratio": rr_ratio, "profit": round(profit_calc, 2),
                    "chart_image_paths": "|".join(saved_urls), "entry_basis": detailed_entry, "exit_basis": detailed_exit
                })
                st.success("성공적으로 저장되었습니다!")
                time.sleep(1); st.rerun()

    st.markdown("---")
    st.markdown("### 📋 전체 매매 내역")
    if not df_trade.empty:
        display_cols = ["date", "ticker", "timeframe", "setup_pattern", "position", "rr_ratio", "result", "profit"]
        selected_event = st.dataframe(df_trade[display_cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        
        if selected_event.get('selection', {}).get('rows', []):
            st.divider()
            trade_data = df_trade.iloc[selected_event['selection']['rows'][0]]
            trade_id = trade_data['id']
            col_t, col_d = st.columns([8.5, 1.5])
            with col_t: st.markdown(f"## 🧐 {trade_data['date']} | {trade_data['ticker']} 복기")
            with col_d:
                if st.button("🗑️ 삭제", type="primary", use_container_width=True, key=f"del_tr_{trade_id}"): delete_db("trade_history", "id", trade_id); st.rerun()
            c_chart, c_memo = st.columns([6, 4], gap="large")
            with c_chart:
                for u in str(trade_data.get("chart_image_paths", "")).split("|"):
                    if u: st.markdown(render_crisp_image_html(u), unsafe_allow_html=True)
            with c_memo:
                with st.form(f"edit_tr_{trade_id}"):
                    e_entry = st.text_area("🟢 진입 근거", trade_data.get("entry_basis", ""), height=150)
                    e_exit = st.text_area("🔴 종료 근거", trade_data.get("exit_basis", ""), height=150)
                    if st.form_submit_button("📝 내용 업데이트"):
                        update_db("trade_history", "id", trade_id, {"entry_basis": e_entry, "exit_basis": e_exit}); st.rerun()

with tab2:
    st.header("🔍 AI 차트 분석 및 관점 피드백 (아카이브 지식 연동)")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        view_uploaded_files = st.file_uploader("📷 차트 이미지 업로드 (여러 장 가능)", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="view_uploader")
        if view_uploaded_files:
            for img in view_uploaded_files: st.image(img, use_container_width=True)
            
    with col2:
        ticker_input = st.text_input("분석할 티커 입력 (예: BTC, NDX)", value=st.session_state.t2_ticker).upper()
        st.session_state.t2_ticker = ticker_input
        user_view = st.text_area("✍️ 현재 나의 관점 (선택)", height=100)
        
        if st.button("🚀 아카이브 기반 AI 관점 분석 요청", type="primary", use_container_width=True):
            keys = get_gemini_keys()
            if not keys:
                st.error("Gemini API 키가 설정되지 않았습니다.")
            elif view_uploaded_files and ticker_input:
                with st.spinner('아카이브에서 관련 자료를 찾고 분석하는 중... 🤖'):
                    try:
                        archive_context = get_recent_archive_context(ticker_input)
                        img_bytes_list, img_objs = [], []
                        for f in view_uploaded_files:
                            b = f.getvalue()
                            img_bytes_list.append({"bytes": b, "name": f.name, "type": getattr(f, 'type', 'image/png')})
                            img_objs.append(Image.open(io.BytesIO(b)))
                        
                        analysis_prompt = f"""
                        당신은 월스트리트 출신의 전문 트레이더이자 멘토입니다. 
                        [종목]: {ticker_input}
                        [나의 관점]: {user_view}
                        {archive_context}
                        
                        반드시 아래 JSON 형식으로만 답변하세요. 마크다운 제외.
                        {{
                          "trend": "상승 / 하락 / 횡보 요약",
                          "key_level": "핵심 지지/저항 요약",
                          "momentum": "모멘텀 상태 요약",
                          "volume": "거래량 상태 요약",
                          "s_score": "0~4 사이 정수",
                          "macro_news": "차트 급등락 시 연관 매크로 이슈 요약. 특이 없으면 '특이 동향 없음'.",
                          "analysis": "1) 종목/타임프레임 명시. 2) 아카이브 근거 기반 조언."
                        }}
                        """
                        st.session_state.ai_result = ask_gemini_dynamic(analysis_prompt, img_objs)
                        st.session_state.ai_analysis_done = True
                        st.session_state.ai_view_text = user_view
                        st.session_state.ai_img_files = img_bytes_list
                        st.rerun()
                    except Exception as e: st.error(f"오류 발생: {e}")
            else: st.warning("⚠️ 차트 업로드 및 '분석할 티커'를 입력해 주세요.")

    if st.session_state.ai_analysis_done:
        st.success("✅ 아카이브 연동 AI 분석 완료!")
        render_ai_advice_block("🤖 AI 멘토의 정밀 피드백", st.session_state.ai_result)
        
        st.divider()
        with st.expander("💾 이 관점을 '나의 관점(Watchlist)'에 저장하기", expanded=True):
            with st.form("save_watchlist_form"):
                c_w1, c_w2 = st.columns(2)
                with c_w1: w_ticker = st.text_input("종목명 (예: BTCUSDT)", value=ticker_input).upper()
                with c_w2: w_date = st.date_input("저장 날짜", datetime.today())
                if st.form_submit_button("🚀 나의 관점(Watchlist)에 저장", type="primary", use_container_width=True):
                    if not w_ticker: st.error("종목명을 입력해주세요!")
                    else:
                        with st.spinner("저장 중..."):
                            class DummyFile:
                                def __init__(self, b, n, t): self.b = b; self.name = n; self.type = t
                                def getvalue(self): return self.b
                            saved_urls = [u for u in [upload_image_to_supabase(DummyFile(fd['bytes'], fd['name'], fd['type']), "watchlist") for fd in st.session_state.ai_img_files] if u]
                            insert_db("analysis_archive", {"date": w_date.strftime("%Y-%m-%d"), "ticker": w_ticker, "category": "나의관점", "source_view": st.session_state.ai_view_text, "chart_image_paths": "|".join(saved_urls), "detail_image_paths": "", "memo": st.session_state.ai_result, "ai_advice_mapping": "{}", "ocr_text_mapping": "{}"})
                            st.session_state.ai_analysis_done = False
                            st.session_state.ai_img_files = [] 
                            st.success("✅ Watchlist에 저장되었습니다!"); st.rerun()

with tab3:
    st.header("📚 나의 매매 기준 & 기본 이론 DB")
    theory_db = load_theory_db()
    col_l, col_r = st.columns([3, 7], gap="large")
    with col_l:
        st.subheader("📑 목차")
        cats = sorted(list(theory_db.keys()))
        sel_cat = st.selectbox("카테고리 선택", cats + ["➕ 새 카테고리 추가"])
        if sel_cat == "➕ 새 카테고리 추가": new_cat_name = st.text_input("새 카테고리명 입력"); sel_title = None
        else:
            titles = list(theory_db[sel_cat].keys())
            sel_title = st.radio("세부 이론 선택", titles) if titles else None
        st.divider()
        with st.expander("📝 새로운 이론 등록/덮어쓰기", expanded=False):
            with st.form("add_th_form", clear_on_submit=True):
                target_cat = sel_cat if sel_cat != "➕ 새 카테고리 추가" else new_cat_name
                th_title = st.text_input("이론 제목")
                th_cont = st.text_area("상세 내용", height=200)
                th_imgs = st.file_uploader("참고 차트 업로드 (선택)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
                if st.form_submit_button("☁️ 클라우드 저장", type="primary"):
                    if th_title and th_cont:
                        img_urls = [u for u in [upload_image_to_supabase(i, "theory") for i in (th_imgs or [])] if u]
                        insert_db("theory_db", {"category": target_cat, "title": th_title, "content": th_cont, "image_paths": "|".join(img_urls)}); st.rerun()
                    else: st.error("제목과 내용을 모두 입력해주세요.")
    with col_r:
        if sel_title and theory_db[sel_cat][sel_title].get("id") is not None:
            data = theory_db[sel_cat][sel_title]
            st.markdown(f"## 📖 {sel_title}")
            st.markdown(data['content'])
            if data['images']:
                st.markdown("<br>### 🖼️ 참고 차트 캡처", unsafe_allow_html=True)
                for u in data['images']:
                    if u: st.markdown(render_crisp_image_html(u), unsafe_allow_html=True)
            if data['id'] != "default":
                with st.expander("⚙️ 이 내용 수정 / 삭제하기", expanded=False):
                    with st.form(f"ed_th_{data['id']}"):
                        ed_cont = st.text_area("내용 수정", value=data['content'], height=250)
                        c_s, c_d = st.columns([7, 3])
                        if c_s.form_submit_button("📝 수정 저장", type="primary", use_container_width=True): update_db("theory_db", "id", data['id'], {"content": ed_cont}); st.rerun()
                        if c_d.form_submit_button("🗑️ 삭제", use_container_width=True): delete_db("theory_db", "id", data['id']); st.rerun()

with tab4:
    st.header("🤖 자동매매 사령실")
    col_status1, col_status2, col_status3, col_status4 = st.columns(4)
    with col_status1:
        bot_on = st.toggle("🚀 봇 가동 스위치 (마스터)", value=False)
        st.markdown(f"**시스템 상태:** {'🟢 작동 중' if bot_on else '🔴 대기 중'}")
    with col_status2: st.metric("오늘의 예상 수익", "+$0.00", "0.0%")
    with col_status3: st.metric("승률", "0.0%", "-")
    with col_status4: st.metric("현재 포지션", "대기 중", "")
    st.divider()
    bot_tab1, bot_tab2, bot_tab3, bot_tab4 = st.tabs(["⚙️ 기본 세팅 (API)", "🛡️ 반자동 생존 매매", "🧠 매매 전략 & 웹훅", "📋 실시간 로그"])
    with bot_tab1:
        with st.form("bot_basic_form", border=True):
            c1, c2 = st.columns(2)
            with c1:
                api_key = st.text_input("Bitget Access Key", type="password", value=st.session_state.get('bg_api', ''))
                secret_key = st.text_input("Bitget Secret Key", type="password", value=st.session_state.get('bg_secret', ''))
            with c2:
                api_passphrase = st.text_input("API Passphrase", type="password", value=st.session_state.get('bg_pass', ''))
                risk_limit = st.slider("허용 리스크 (시드의 %)", 0.1, 5.0, 1.0, 0.1)
            if st.form_submit_button("세팅 저장", type="primary"):
                st.session_state['bg_api'], st.session_state['bg_secret'], st.session_state['bg_pass'], st.session_state['bg_risk'] = api_key, secret_key, api_passphrase, risk_limit
                st.success("API 세팅 활성화 완료!")
    with bot_tab2:
        with st.form("survival_trade_form"):
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1: sv_symbol = st.text_input("종목 (예: BTC/USDT:USDT)", value="BTC/USDT:USDT")
            with col_s2: sv_side = st.selectbox("포지션", ["buy (Long)", "sell (Short)"])
            with col_s3: sv_sl_percent = st.number_input("손절 비율 (%)", 0.1, 10.0, 2.0, 0.1)
            sv_reason = st.text_area("진입 근거", placeholder="매매 일지 자동 기록")
            if st.form_submit_button("🚀 진입 및 스탑로스 세팅", type="primary", use_container_width=True):
                if not st.session_state.get('bg_api'): st.error("API 키를 저장해주세요.")
                else:
                    with st.spinner("전송 중..."):
                        success, msg = execute_survival_trade(st.session_state['bg_api'], st.session_state['bg_secret'], st.session_state['bg_pass'], sv_symbol, "buy" if "buy" in sv_side else "sell", sv_sl_percent, sv_reason, st.session_state.get('bg_risk', 1.0))
                        if success: st.success(msg)
                        else: st.error(msg)
    with bot_tab3:
        c_hook, c_strat = st.columns([6, 4])
        with c_hook: st.code("https://youngwoo-trading.streamlit.app/api/webhook\n\n{\n  \"action\": \"long\",\n  \"ticker\": \"BTCUSDT\"\n}", language="json")
        with c_strat:
            st.selectbox("전략 선택", ["Webhook 전용", "AI 감시 결합형"])
            st.button("전략 저장")
    with bot_tab4:
        st.code("[System] 봇 모듈 활성화 완료...", language="bash")

with tab5:
    st.header("📁 분석 자료 아카이브 (AI 자동화)")
    df_archive = load_archive_data()
    sub_tab_a, sub_tab_b = st.tabs(["👨‍🏫 타인 분석 스크랩", "👀 나의 관점 (Watchlist)"])
    with sub_tab_a:
        with st.expander("➕ 새로운 스크랩 추가하기", expanded=False):
            col_header, col_reset = st.columns([8, 2])
            with col_header: st.markdown("### 📝 새 분석 스크랩 작성")
            with col_reset:
                if st.button("🗑️ 첨부 일괄 삭제", use_container_width=True): st.session_state.uploader_key += 1; st.rerun()
            col_up1, col_up2 = st.columns(2)
            with col_up1: arch_imgs_blog = st.file_uploader("인사이트 원본 글", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key=f"arch_imgs_blog_{st.session_state.uploader_key}")
            with col_up2: arch_imgs_detail = st.file_uploader("세부 고해상도 차트", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key=f"arch_imgs_detail_{st.session_state.uploader_key}")
            with st.form("archive_form_others", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)
                with col1: arch_date1 = st.date_input("스크랩 날짜", datetime.today())
                with col2: arch_ticker1 = st.text_input("관련 종목명 (예: BTC)").upper()
                with col3: arch_source1 = st.text_input("출처/제목")
                
                ticker_mapping_input, selected_charts_for_ai = {}, []
                if arch_imgs_detail:
                    batch_ticker = st.text_input("💡 [일괄 적용] 모든 차트에 적용할 종목명")
                    cols = st.columns(3)
                    for idx, img in enumerate(arch_imgs_detail):
                        selected_charts_for_ai.append(img.name)
                        with cols[idx % 3]: ticker_mapping_input[img.name] = st.text_input(f"차트 {idx+1}", key=f"t_{st.session_state.uploader_key}_{idx}")
                if st.form_submit_button("☁️ 스크랩 & 무료 AI 분석 시작", use_container_width=True, type="primary"):
                    if not arch_ticker1: st.error("종목명을 1개 이상 입력해주세요!")
                    else:
                        with st.spinner("AI 분석 중... 🤖"):
                            blog_urls, detail_urls, ai_advice_final_mapping, ocr_final_mapping = [], [], {}, {}
                            if arch_imgs_blog:
                                for img_file in sorted(arch_imgs_blog, key=lambda x: int(get_file_group_info(x.name)[0]) if str(get_file_group_info(x.name)[0]).isdigit() else 9999):
                                    g, s = get_file_group_info(img_file.name)
                                    url = upload_image_to_supabase(img_file, f"arch_blog_{g}_{s}")
                                    if url: blog_urls.append(url); ocr_final_mapping[g] = get_real_ocr_text(url)
                            if arch_imgs_detail:
                                for img_file in arch_imgs_detail:
                                    g, s = get_file_group_info(img_file.name)
                                    url = upload_image_to_supabase(img_file, f"arch_detail_{g}_{s}")
                                    if url:
                                        detail_urls.append(url)
                                        spec_ticker = ticker_mapping_input.get(img_file.name, "").strip() or batch_ticker.strip() or arch_ticker1.strip()
                                        ai_advice_final_mapping[f"{g}_{s}"] = get_real_ai_advice(url, spec_ticker, ocr_final_mapping.get(g, ""))
                            insert_db("analysis_archive", {"date": arch_date1.strftime("%Y-%m-%d"), "ticker": arch_ticker1, "category": "타인분석", "source_view": arch_source1, "chart_image_paths": "|".join(blog_urls), "detail_image_paths": "|".join(detail_urls), "memo": "", "ai_advice_mapping": json.dumps(ai_advice_final_mapping, ensure_ascii=False), "ocr_text_mapping": json.dumps(ocr_final_mapping, ensure_ascii=False)})
                            st.session_state.uploader_key += 1; st.success("저장 완료!"); st.rerun()

        df_others = df_archive[df_archive['category'] == '타인분석'].copy()
        if not df_others.empty:
            df_others = df_others.sort_values(by='date', ascending=False).reset_index(drop=True)
            sel_other = st.dataframe(df_others[["date", "ticker", "source_view"]], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
            if sel_other.get('selection', {}).get('rows', []):
                arch_data = df_others.iloc[sel_other['selection']['rows'][0]]
                arch_id = arch_data['id']
                st.markdown(f"## 📚 {arch_data['date']} | {arch_data['ticker']} 분석 스크랩")
                if st.button("🗑️ 삭제하기"): delete_db("analysis_archive", "id", arch_id); st.rerun()
                
                valid_blogs = [p for p in str(arch_data.get("chart_image_paths", "")).split("|") if p]
                valid_details = [p for p in str(arch_data.get("detail_image_paths", "")).split("|") if p]
                ai_map = json.loads(arch_data.get("ai_advice_mapping", "{}")) if isinstance(arch_data.get("ai_advice_mapping"), str) else {}
                ocr_map = json.loads(arch_data.get("ocr_text_mapping", "{}")) if isinstance(arch_data.get("ocr_text_mapping"), str) else {}
                
                det_dict = {}
                for dp in valid_details:
                    g = dp.split('_detail_')[1].split('_')[0] if '_detail_' in dp else "0"
                    s = int(dp.split('_detail_')[1].split('_')[1].split('.')[0]) if '_detail_' in dp and len(dp.split('_detail_')[1].split('_'))>1 else 0
                    if g not in det_dict: det_dict[g] = []
                    det_dict[g].append((s, dp))
                for g in det_dict: det_dict[g] = [x[1] for x in sorted(det_dict[g])]
                
                for idx, path in enumerate(valid_blogs):
                    g = path.split('_blog_')[1].split('_')[0] if '_blog_' in path else str(idx)
                    st.markdown("---")
                    c_blog, c_ocr = st.columns([4, 6])
                    with c_blog: st.markdown(render_blog_image_html(path), unsafe_allow_html=True)
                    with c_ocr:
                        for _, mdp in sorted(det_dict.get(g, [])): st.markdown(render_crisp_image_html(mdp), unsafe_allow_html=True)
                        if g in ai_map: render_ai_advice_block("🤖 AI 분석", ai_map[g])
                        st.info(ocr_map.get(g, "추출된 텍스트가 없습니다."))

    with sub_tab_b:
        st.markdown("### 👀 나의 관점 (Watchlist)")
        df_myview = df_archive[df_archive['category'] == '나의관점'].copy()
        if not df_myview.empty:
            sel_my = st.dataframe(df_myview[["date", "ticker", "source_view"]], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
            if sel_my.get('selection', {}).get('rows', []):
                my_data = df_myview.iloc[sel_my['selection']['rows'][0]]
                st.markdown(f"## 🎯 {my_data['date']} | {my_data['ticker']} 관점")
                if st.button("🗑️ 삭제하기", key=f"del_my_{my_data['id']}"): delete_db("analysis_archive", "id", my_data['id']); st.rerun()
                c_img, c_txt = st.columns([6, 4])
                with c_img:
                    for u in str(my_data.get('chart_image_paths', '')).split('|'):
                        if u: st.markdown(render_crisp_image_html(u), unsafe_allow_html=True)
                with c_txt:
                    st.info(f"**💡 나의 셋업 관점:**\n{my_data['source_view']}")
                    render_ai_advice_block("🤖 검증 피드백", my_data['memo'])

with tab6:
    st.header("🏢 섹터 & 주도주 맵 (AI 리서치 저장소)")
    st.info("야후 파이낸스(yfinance)를 통해 4H/1D 이평선 크로스, 실적, 최신 뉴스를 긁어오고 AI가 심층 리포트를 작성합니다.")
    
    with st.expander("➕ 새 종목 리서치 자동화 추가하기"):
        with st.form("new_sector_stock"):
            c1, c2 = st.columns(2)
            s_ticker = c1.text_input("야후 파이낸스 티커 (예: NVDA, AAPL, BTC-USD)")
            s_sector = c2.selectbox("섹터 분류", ["AI", "소프트웨어", "반도체", "조선", "헬스케어", "코인", "기타"])
            
            s_issue = st.text_area("🔥 내가 주목하는 핵심 이슈 (나만의 투자 관점)", height=100)
            
            if st.form_submit_button("🤖 금융 데이터 자동 긁어오기 & AI 리서치 시작", type="primary"):
                if s_ticker:
                    # 💡 영우님의 SaveTicker 계정 완전 하드코딩
                    st_id = "swsecret@naver.com"
                    st_pw = "1!REre4423"
                    
                    with st.spinner("데이터 수집 및 크로스체크 분석 중... (최대 1~2분 소요)"):
                        fin_data = fetch_financial_data(s_ticker.strip())
                        st_news_content = fetch_saveticker_news(st_id, st_pw)
                        
                        if "error" in fin_data: st.error(f"데이터 수집 실패: {fin_data['error']}")
                        else:
                            ai_res = analyze_sector_with_ai(s_ticker, s_sector, fin_data, s_issue, st_news_content)
                            
                            left_column_html = f"""
                            <div class='info-card'><h4>📈 이평선 분석 (4H MA200 vs 1D MA200)</h4>{fin_data.get('ma_html', '')}</div>
                            <div class='info-card'><h4>📊 가격 및 거래량 모멘텀</h4>{fin_data.get('momentum_html', '')}</div>
                            <div class='info-card'><h4>💰 실적(Earnings) 데이터</h4>{fin_data.get('earnings_html', '')}</div>
                            <div class='info-card'><h4>🔥 나의 메모 및 투자 관점</h4><p>{s_issue}</p></div>
                            """
                            
                            insert_db("sector_analysis", {
                                "ticker": s_ticker.upper(), "sector": s_sector, "market_cap": fin_data.get('market_cap', ''),
                                "vol_1d": "", "vol_1w": "", "vol_1m": "", "vol_1q": "", "vol_1y": "",
                                "issue": left_column_html, "detail_data": fin_data.get('raw_news', ''), "ai_analysis": ai_res
                            })
                            st.success("리서치 리포트 등록 완료!"); time.sleep(1); st.rerun()

    df_sector = load_sector_data()
    if not df_sector.empty:
        filter_sec = st.selectbox("섹터 필터링", ["전체"] + list(df_sector['sector'].unique()))
        if filter_sec != "전체": df_sector = df_sector[df_sector['sector'] == filter_sec]
            
        disp_cols = ["ticker", "sector", "market_cap"]
        sel_stock = st.dataframe(df_sector[disp_cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        
        if sel_stock.get('selection', {}).get('rows', []):
            st.divider()
            stock_data = df_sector.iloc[sel_stock['selection']['rows'][0]]
            s_id = stock_data['id']
            
            col_st1, col_st2 = st.columns([8, 2])
            with col_st1:
                st.markdown(f"## 🏢 {stock_data['ticker']} 리서치 리포트")
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
              "hide_top_toolbar": false, "hide_legend": false, "save_image": false, "container_id": "tradingview_{stock_data['ticker']}"
              }});
              </script>
            </div>
            """
            components.html(tv_widget, height=650)
            
            st.markdown("---")
            c_left, c_right = st.columns([4, 6], gap="large")
            with c_left:
                st.markdown(stock_data['issue'], unsafe_allow_html=True)
                with st.expander("📰 AI가 팩트체크한 원문 뉴스 (Yahoo, Investing.com)", expanded=False):
                    st.write(stock_data.get('detail_data', '수집된 뉴스가 없습니다.'))
            with c_right:
                if stock_data.get('ai_analysis'):
                    st.markdown("#### 🤖 AI 월스트리트 애널리스트 분석")
                    st.markdown(stock_data['ai_analysis'], unsafe_allow_html=True)
