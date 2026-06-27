import streamlit as st

import pandas as pd

import json

import uuid

import os

import io

import time

from datetime import datetime

from PIL import Image



# 👇 API 유틸리티 모듈 불러오기

from api_utils import (

    insert_db, update_db, delete_db, upload_image_to_supabase,

    load_trade_data, load_archive_data, get_recent_archive_context, load_theory_db,

    get_gemini_keys, parse_ai_json, ask_gemini_dynamic, get_real_ocr_text, 

    get_real_ai_advice, render_ai_advice_block, render_blog_image_html, 

    render_crisp_image_html, get_file_group_info, execute_survival_trade

)



# 👇 방금 새로 분리한 3개의 탭(Tab) 모듈 불러오기!

from tab_research import render_research_tab

from tab_us import render_us_map_tab

from tab_kr import render_kr_map_tab

from tab_crypto import render_crypto_map_tab



# ==========================================

# --- 1. 화면 구성 및 기본 세팅 (UI) ---

# ==========================================

st.set_page_config(page_title="나만의 트레이딩 대시보드", layout="wide")



st.markdown("""

<style>

div[data-testid="stInfo"] p { font-size: 1.1rem; } 

div[data-testid="stError"] p { font-size: 1.1rem; }

div[data-testid="stMetricValue"] { font-size: 1.2rem !important; }

div[data-testid="stMetricLabel"] { font-size: 0.85rem !important; color: #666; }



.info-card { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 25px; margin-bottom: 25px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }

.info-card h4 { color: #1e40af; margin-top: 0; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; font-size: 1.3rem; }

.ma-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 1.05rem; }

.ma-table th, .ma-table td { border: 1px solid #cbd5e1; padding: 12px 15px; text-align: left; }

.ma-table th { background-color: #e2e8f0; font-weight: bold; color: #1e293b; text-align: center; }

.ma-table tr:nth-child(even) { background-color: #f8fafc; }

.ma-table tr:hover { background-color: #f1f5f9; }

</style>

""", unsafe_allow_html=True)



st.title("📈 나만의 클라우드 매매 복기 & 자동 AI 분석 시스템")



# 세션 스테이트 초기화

if "ai_analysis_done" not in st.session_state:

    st.session_state.ai_analysis_done = False

    st.session_state.ai_result = ""

    st.session_state.ai_view_text = ""

    st.session_state.ai_img_files = [] 

if "uploader_key" not in st.session_state: st.session_state.uploader_key = 0 

if "sp100_state_df" not in st.session_state: st.session_state.sp100_state_df = pd.DataFrame()

if "kospi100_state_df" not in st.session_state: st.session_state.kospi100_state_df = pd.DataFrame()



# 전체 탭 구성

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([

    "📝 매매 기록 보관지", "🔎 AI 차트 & 관점 분석", "📚 기본 이론 & DB", 

    "🤖 자동매매 사령실", "📁 분석 자료 아카이브", "🏢 섹터 & 주도주 맵"

])



# ==========================================

# --- Tab 1: 매매 기록 보관지 ---

# ==========================================

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

            

            if profit_calc > 0: auto_res = "승"

            elif profit_calc < 0: auto_res = "패"

            else: auto_res = "무"

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

                saved_urls = [upload_image_to_supabase(img, "trade") for img in (uploaded_images or [])]

                saved_urls = [u for u in saved_urls if u]

                detailed_entry = f"[진입가: {entry_price} | 레버리지: {leverage}x | 원금: ${margin}]\n{entry_basis}"

                detailed_exit = f"[종료가: {exit_price}]\n{exit_basis}"

                insert_db("trade_history", {

                    "date": date.strftime("%Y-%m-%d"), "ticker": ticker, "timeframe": timeframe, 

                    "setup_pattern": setup_pattern, "position": position, "result": result, 

                    "rr_ratio": rr_ratio, "profit": round(profit_calc, 2), "chart_image_paths": "|".join(saved_urls), 

                    "entry_basis": detailed_entry, "exit_basis": detailed_exit

                })

                st.success("성공적으로 저장되었습니다!"); time.sleep(1); st.rerun()



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

                if st.button("🗑️ 삭제", type="primary", use_container_width=True, key=f"del_tr_{trade_id}"):

                    delete_db("trade_history", "id", trade_id); st.rerun()

            

            c_chart, c_memo = st.columns([6, 4], gap="large")

            with c_chart:

                for u in str(trade_data.get("chart_image_paths", "")).split("|"):

                    if u: st.markdown(render_crisp_image_html(u), unsafe_allow_html=True)

            with c_memo:

                with st.form(f"edit_tr_{trade_id}"):

                    e_entry = st.text_area("🟢 진입 근거", value=trade_data.get("entry_basis", ""), height=150)

                    e_exit = st.text_area("🔴 종료 근거", value=trade_data.get("exit_basis", ""), height=150)

                    if st.form_submit_button("📝 내용 업데이트"):

                        update_db("trade_history", "id", trade_id, {"entry_basis": e_entry, "exit_basis": e_exit}); st.rerun()



# ==========================================

# --- Tab 2: AI 차트 & 관점 분석 ---

# ==========================================

with tab2:

    st.header("🔍 AI 차트 분석 및 관점 피드백 (아카이브 지식 연동)")

    col1, col2 = st.columns([1, 1])

    with col1:

        view_uploaded_files = st.file_uploader("📷 차트 이미지 업로드 (여러 장 드래그 가능)", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="view_uploader")

        if view_uploaded_files:

            for img in view_uploaded_files: st.image(img, caption=img.name, use_container_width=True)

    with col2:

        ticker_input = st.text_input("분석할 티커 입력 (예: BTC, NDX)").upper()

        user_view = st.text_area("✍️ 현재 나의 관점", height=100)

        if st.button("🚀 아카이브 기반 AI 관점 분석 요청", type="primary", use_container_width=True):

            keys = get_gemini_keys()

            if not keys: st.error("Gemini API 키가 설정되지 않았습니다.")

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

                        당신은 월스트리트 출신의 전문 트레이더입니다. [종목]: {ticker_input} [나의 관점]: {user_view} {archive_context}

                        반드시 JSON 형식으로만 출력하세요.

                        {{ "trend": "...", "key_level": "...", "momentum": "...", "volume": "...", "s_score": 3, "macro_news": "...", "analysis": "..." }}

                        """

                        analysis_result = ask_gemini_dynamic(analysis_prompt, img_objs)

                        st.session_state.ai_analysis_done = True

                        st.session_state.ai_result = analysis_result

                        st.session_state.ai_view_text = user_view

                        st.session_state.ai_img_files = img_bytes_list

                        st.rerun()

                    except Exception as e: st.error(f"분석 중 오류가 발생했습니다: {e}")

            else: st.warning("⚠️ 차트 이미지와 티커를 입력해주세요.")



    if st.session_state.ai_analysis_done:

        st.success("✅ 아카이브 연동 AI 분석 완료!")

        render_ai_advice_block("🤖 AI 멘토의 정밀 피드백", st.session_state.ai_result)

        st.divider()

        with st.expander("💾 이 관점을 '나의 관점(Watchlist)'에 저장하기", expanded=True):

            with st.form("save_watchlist_form"):

                col_w1, col_w2 = st.columns(2)

                with col_w1: w_ticker = st.text_input("종목명", value=ticker_input).upper()

                with col_w2: w_date = st.date_input("저장 날짜", datetime.today())

                if st.form_submit_button("🚀 나의 관점(Watchlist)에 저장", type="primary", use_container_width=True):

                    if w_ticker:

                        with st.spinner("클라우드 보관 중..."):

                            class DummyFile:

                                def __init__(self, b, n, t): self.b = b; self.name = n; self.type = t

                                def getvalue(self): return self.b

                            saved_urls = []

                            for file_data in st.session_state.ai_img_files:

                                dummy_img = DummyFile(file_data['bytes'], file_data['name'], file_data['type'])

                                img_url = upload_image_to_supabase(dummy_img, "watchlist")

                                if img_url: saved_urls.append(img_url)

                            insert_db("analysis_archive", {

                                "date": w_date.strftime("%Y-%m-%d"), "ticker": w_ticker, "category": "나의관점", 

                                "source_view": st.session_state.ai_view_text, "chart_image_paths": "|".join(saved_urls), 

                                "detail_image_paths": "", "memo": st.session_state.ai_result, 

                                "ai_advice_mapping": "{}", "ocr_text_mapping": "{}"

                            })

                            st.session_state.ai_analysis_done = False; st.session_state.ai_img_files = []

                            st.success("✅ Watchlist 저장 완료!"); st.rerun()



# ==========================================

# --- Tab 3: 기본 이론 & DB ---

# ==========================================

with tab3:

    st.header("📚 나의 매매 기준 & 기본 이론 DB")

    theory_db = load_theory_db()

    col_l, col_r = st.columns([3, 7], gap="large")



    with col_l:

        st.subheader("📑 목차")

        cats = list(theory_db.keys())

        cats.sort()

        sel_cat = st.selectbox("카테고리 선택", cats + ["➕ 새 카테고리 추가"])

        if sel_cat == "➕ 새 카테고리 추가":

            new_cat_name = st.text_input("새 카테고리명 입력")

            sel_title = None

        else:

            titles = list(theory_db[sel_cat].keys())

            sel_title = st.radio("세부 이론 선택", titles) if titles else None



        st.divider()

        with st.expander("📝 새로운 이론 등록/덮어쓰기", expanded=False):

            with st.form("add_th_form", clear_on_submit=True):

                target_cat = sel_cat if sel_cat != "➕ 새 카테고리 추가" else new_cat_name

                th_title = st.text_input("이론 제목 (목차 이름과 동일하게 입력)")

                th_cont = st.text_area("상세 내용", height=200)

                th_imgs = st.file_uploader("참고 차트 업로드 (선택)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

                if st.form_submit_button("☁️ 클라우드 저장", type="primary"):

                    if th_title and th_cont:

                        img_urls = [upload_image_to_supabase(i, "theory") for i in (th_imgs or [])]

                        insert_db("theory_db", {"category": target_cat, "title": th_title, "content": th_cont, "image_paths": "|".join([u for u in img_urls if u])})

                        st.rerun()



    with col_r:

        if sel_title and theory_db[sel_cat][sel_title].get("id") is not None:

            data = theory_db[sel_cat][sel_title]

            st.markdown(f"## 📖 {sel_title}")

            st.divider(); st.markdown(data['content'])

            if data['images']:

                st.markdown("<br>### 🖼️ 참고 차트 캡처", unsafe_allow_html=True)

                for u in data['images']:

                    if u: st.markdown(render_crisp_image_html(u), unsafe_allow_html=True)

            if data['id'] != "default":

                with st.expander("⚙️ 이 내용 수정 / 삭제하기", expanded=False):

                    with st.form(f"ed_th_{data['id']}"):

                        ed_cont = st.text_area("내용 수정", value=data['content'], height=250)

                        c_s, c_d = st.columns([7, 3])

                        if c_s.form_submit_button("📝 수정 내용 저장", type="primary", use_container_width=True):

                            update_db("theory_db", "id", data['id'], {"content": ed_cont}); st.rerun()

                        if c_d.form_submit_button("🗑️ 이 이론 삭제", use_container_width=True):

                            delete_db("theory_db", "id", data['id']); st.rerun()



# ==========================================

# --- Tab 4: 자동매매 사령실 ---

# ==========================================

with tab4:

    st.header("🤖 자동매매 사령실 (컨트롤 패널)")

    col_status1, col_status2, col_status3, col_status4 = st.columns(4)

    with col_status1: bot_on = st.toggle("🚀 봇 가동 스위치 (마스터)", value=False)

    with col_status2: st.metric("오늘의 예상 수익", "+$0.00", "0.0%")

    with col_status3: st.metric("승률 (최근 10건)", "0.0%", "-")

    with col_status4: st.metric("현재 포지션", "대기 중 (Flat)", "")

    st.divider()



    bot_tab1, bot_tab2, bot_tab3, bot_tab4 = st.tabs(["⚙️ 기본 세팅 (API)", "🛡️ 반자동 생존 매매", "🧠 매매 전략 & 웹훅", "📋 실시간 작동 로그"])

    with bot_tab1:

        with st.form("bot_basic_form", border=True):

            c1, c2 = st.columns(2)

            with c1:

                api_key = st.text_input("Bitget API Key", type="password", value=st.session_state.get('bg_api', ''))

                secret_key = st.text_input("Bitget Secret Key", type="password", value=st.session_state.get('bg_secret', ''))

            with c2:

                api_passphrase = st.text_input("API Passphrase", type="password", value=st.session_state.get('bg_pass', ''))

                risk_limit = st.slider("1회 진입 허용 리스크 (%)", 0.1, 5.0, 1.0, 0.1)

            if st.form_submit_button("세션 저장", type="primary"):

                st.session_state.update({'bg_api': api_key, 'bg_secret': secret_key, 'bg_pass': api_passphrase, 'bg_risk': risk_limit})

                st.success("API 세팅 완료!")

    with bot_tab2:

        with st.form("survival_trade_form"):

            col_s1, col_s2, col_s3 = st.columns(3)

            with col_s1: sv_symbol = st.text_input("종목명", value="BTC/USDT:USDT")

            with col_s2: sv_side = st.selectbox("포지션", ["buy (Long)", "sell (Short)"])

            with col_s3: sv_sl_percent = st.number_input("손절 비율 (%)", 0.1, 10.0, 2.0, 0.1)

            sv_reason = st.text_area("진입 근거", placeholder="예: 스윕 확인 후 진입")

            if st.form_submit_button("🚀 진입 및 스탑로스 자동 세팅", type="primary", use_container_width=True):

                if not st.session_state.get('bg_api'): st.error("API 키를 저장해주세요.")

                else:

                    success, msg = execute_survival_trade(st.session_state['bg_api'], st.session_state['bg_secret'], st.session_state['bg_pass'], sv_symbol, "buy" if "buy" in sv_side else "sell", sv_sl_percent, sv_reason, st.session_state.get('bg_risk', 1.0))

                    if success: st.success(msg)

                    else: st.error(msg)

    with bot_tab3:

        st.code("https://youngwoo-trading.streamlit.app/webhook", language="text")

    with bot_tab4:

        st.code("[System] 봇 모듈 준비 완료...", language="bash")



# ==========================================

# --- Tab 5: 분석 자료 아카이브 ---

# ==========================================

with tab5:

    st.header("📁 분석 자료 아카이브 (AI 자동화)")

    df_archive = load_archive_data()

    sub_tab_a, sub_tab_b = st.tabs(["👨‍🏫 타인 분석 스크랩", "👀 나의 관점 (Watchlist)"])

    

    with sub_tab_a:

        with st.expander("➕ 새로운 스크랩 추가하기", expanded=False):

            with st.form("archive_form_others", clear_on_submit=True):

                col1, col2, col3 = st.columns(3)

                with col1: arch_date1 = st.date_input("스크랩 날짜", datetime.today())

                with col2: arch_ticker1 = st.text_input("종목명").upper()

                with col3: arch_source1 = st.text_input("출처/제목")

                

                arch_imgs_blog = st.file_uploader("인사이트 내용 캡처 (블로그 글 등)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

                arch_imgs_detail = st.file_uploader("고해상도 차트 캡처", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

                

                if st.form_submit_button("☁️ 스크랩 & 무료 AI 분석 시작", type="primary"):

                    if not arch_ticker1: st.error("관련 종목명을 최소 1개 이상 입력해주세요!")

                    else:

                        with st.spinner("AI 분석 및 클라우드 저장 중..."):

                            blog_urls, detail_urls = [], []

                            ocr_map, ai_map = {}, {}

                            

                            for img in (arch_imgs_blog or []):

                                group, sub = get_file_group_info(img.name)

                                url = upload_image_to_supabase(img, f"arch_blog_{group}_{sub}")

                                if url: 

                                    blog_urls.append(url)

                                    ocr_map[group] = get_real_ocr_text(url)

                            

                            for img in (arch_imgs_detail or []):

                                group, sub = get_file_group_info(img.name)

                                url = upload_image_to_supabase(img, f"arch_detail_{group}_{sub}")

                                if url:

                                    detail_urls.append(url)

                                    assoc_text = ocr_map.get(group, "")

                                    ai_map[f"{group}_{sub}"] = get_real_ai_advice(url, arch_ticker1, assoc_text)

                            

                            insert_db("analysis_archive", {

                                "date": arch_date1.strftime("%Y-%m-%d"), "ticker": arch_ticker1, "category": "타인분석", 

                                "source_view": arch_source1, "chart_image_paths": "|".join(blog_urls), "detail_image_paths": "|".join(detail_urls), 

                                "memo": "", "ai_advice_mapping": json.dumps(ai_map, ensure_ascii=False), "ocr_text_mapping": json.dumps(ocr_map, ensure_ascii=False)

                            })

                            st.success("완료!"); time.sleep(1); st.rerun()



        df_others = df_archive[df_archive['category'] == '타인분석'].copy()

        if not df_others.empty:

            df_others = df_others.sort_values(by='date', ascending=False).reset_index(drop=True)

            selected_other = st.dataframe(df_others[["date", "ticker", "source_view"]], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

            if selected_other.get('selection', {}).get('rows', []):

                arch_data = df_others.iloc[selected_other['selection']['rows'][0]]

                arch_id = arch_data['id']

                st.divider()

                col_t, col_d = st.columns([8.5, 1.5])

                with col_t: st.markdown(f"## 📚 {arch_data['date']} | {arch_data['ticker']} 분석 스크랩")

                with col_d:

                    if st.button("🗑️ 삭제", key=f"del_arch_{arch_id}", type="primary", use_container_width=True):

                        delete_db("analysis_archive", "id", arch_id); st.rerun()

                

                # 블로그 이미지 렌더링

                blog_paths = [p for p in str(arch_data.get("chart_image_paths", "")).split("|") if p]

                detail_paths = [p for p in str(arch_data.get("detail_image_paths", "")).split("|") if p]

                try: ocr_map = json.loads(arch_data.get("ocr_text_mapping", "{}"))

                except: ocr_map = {}

                try: ai_map = json.loads(arch_data.get("ai_advice_mapping", "{}"))

                except: ai_map = {}

                

                for idx, path in enumerate(blog_paths):

                    group = path.split('_blog_')[1].split('_')[0] if '_blog_' in path else str(idx)

                    st.markdown("---")

                    st.markdown(f"#### 📄 원본 데이터 {idx+1}")

                    st.markdown(render_blog_image_html(path), unsafe_allow_html=True)

                    if group in ocr_map and ocr_map[group]: st.info(ocr_map[group])

                

                for idx, path in enumerate(detail_paths):

                    st.markdown("---")

                    st.markdown(f"#### 🔍 세부 차트 분석 {idx+1}")

                    c_chart, c_ai = st.columns([6, 4], gap="medium")

                    with c_chart: st.markdown(render_crisp_image_html(path), unsafe_allow_html=True)

                    with c_ai:

                        fname = path.split('/')[-1]

                        parts = fname.split('_detail_')[1].split('_') if '_detail_' in fname else []

                        key = f"{parts[0]}_{int(parts[1]) if len(parts)>1 and parts[1].isdigit() else 0}" if parts else ""

                        if key in ai_map and ai_map[key]: render_ai_advice_block("🤖 AI 조언", ai_map[key])

                        else: st.write("AI 분석 결과 없음")



    with sub_tab_b:

        st.markdown("### 👀 나의 관점 (Watchlist)")

        df_my = df_archive[df_archive['category'] == '나의관점'].copy()

        if not df_my.empty:

            selected_my = st.dataframe(df_my[["date", "ticker", "source_view"]], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")

            if selected_my.get('selection', {}).get('rows', []):

                my_data = df_my.iloc[selected_my['selection']['rows'][0]]

                st.divider()

                st.markdown(f"## 🎯 {my_data['date']} | {my_data['ticker']} 관점")

                for u in str(my_data.get("chart_image_paths", "")).split("|"):

                    if u: st.markdown(render_crisp_image_html(u), unsafe_allow_html=True)

                st.info(f"💡 나의 관점:\n\n{my_data['source_view']}")

                if my_data.get('memo'): render_ai_advice_block("🤖 AI 피드백", my_data['memo'])



# ==========================================

# --- Tab 6: 섹터 & 주도주 맵 (🚨 새로 분리한 3개의 모듈 탑재) ---

# ==========================================

with tab6:

    st.header("🏢 섹터 & 주도주 맵 (AI 리서치 저장소)")

    st.info("야후 파이낸스(yfinance)와 트레이딩뷰 실시간 스캐너를 통해 시장을 정밀 타격합니다.")

    

    sub_tab_research, sub_tab_top100, sub_tab_kr_top100, sub_tab_crypto = st.tabs([

        "🏢 내 종목 리서치", "🇺🇸 미국 시총 Top 100 맵", "🇰🇷 한국 코스피 Top 100 맵", "🪙 암호화폐 Top 100 맵"

    ])

    

    with sub_tab_research:

        # 방금 만든 tab_research.py 의 기능을 불러와 그립니다.

        render_research_tab()

        

    with sub_tab_top100:

        # 방금 만든 tab_us.py 의 기능을 불러와 그립니다.

        render_us_map_tab()

        

    with sub_tab_kr_top100:

        # 방금 만든 tab_kr.py 의 기능을 불러와 그립니다.

        render_kr_map_tab()

        

    with sub_tab_crypto:

        # 방금 만든 tab_crypto.py 의 기능을 불러와 그립니다.

        render_crypto_map_tab() 

