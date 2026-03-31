import streamlit as st
import pandas as pd
import requests
import json
import uuid
import re
import os
import io
from datetime import datetime
from PIL import Image
import google.generativeai as genai

# ==========================================
# --- 1. 클라우드 및 무료 AI(Gemini) 세팅 ---
# ==========================================
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# 구글 Gemini AI 키 세팅
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# ==========================================
# --- 2. 클라우드 DB 통신 도우미 함수들 ---
# ==========================================
def insert_db(table, data):
    return requests.post(f"{URL}/rest/v1/{table}", headers=HEADERS, json=data)

def update_db(table, match_col, match_val, data):
    return requests.patch(f"{URL}/rest/v1/{table}?{match_col}=eq.{match_val}", headers=HEADERS, json=data)

def delete_db(table, match_col, match_val):
    return requests.delete(f"{URL}/rest/v1/{table}?{match_col}=eq.{match_val}", headers=HEADERS)

def upload_image_to_supabase(img_file, prefix="img"):
    try:
        file_ext = img_file.name.split('.')[-1]
        file_name = f"{prefix}_{uuid.uuid4().hex[:8]}.{file_ext}"
        file_bytes = img_file.getvalue()
        
        upload_url = f"{URL}/storage/v1/object/chart_images/{file_name}"
        img_headers = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": img_file.type}
        
        res = requests.post(upload_url, headers=img_headers, data=file_bytes)
        if res.status_code == 200:
            return f"{URL}/storage/v1/object/public/chart_images/{file_name}"
        return None
    except Exception:
        return None

# ==========================================
# --- 3. 데이터 로드 함수 ---
# ==========================================
def load_trade_data():
    res = requests.get(f"{URL}/rest/v1/trade_history?select=*&order=created_at.desc", headers=HEADERS)
    if res.status_code == 200 and res.json(): return pd.DataFrame(res.json())
    return pd.DataFrame(columns=["id", "date", "ticker", "timeframe", "setup_pattern", "position", "result", "rr_ratio", "profit", "chart_image_paths", "entry_basis", "exit_basis"])

def load_archive_data():
    res = requests.get(f"{URL}/rest/v1/analysis_archive?select=*&order=created_at.desc", headers=HEADERS)
    if res.status_code == 200 and res.json():
        df = pd.DataFrame(res.json())
        if 'ai_advice_mapping' not in df.columns: df['ai_advice_mapping'] = "{}"
        if 'ocr_text_mapping' not in df.columns: df['ocr_text_mapping'] = "{}"
        return df
    return pd.DataFrame(columns=["id", "date", "ticker", "category", "source_view", "chart_image_paths", "detail_image_paths", "memo", "ai_advice_mapping", "ocr_text_mapping"])

def load_theory_db():
    res = requests.get(f"{URL}/rest/v1/theory_db?select=*", headers=HEADERS)
    db_dict = {}
    if res.status_code == 200 and res.json():
        for row in res.json():
            cat, title = row['category'], row['title']
            if cat not in db_dict: db_dict[cat] = {}
            db_dict[cat][title] = {"content": row.get('content', ''), "images": row.get('image_paths', '').split('|') if row.get('image_paths') else []}
    else:
        db_dict = {"기본 카테고리": {"환영합니다!": {"content": "새로운 이론을 추가해 보세요.", "images": []}}}
    return db_dict

# ==========================================
# --- 4. 🚀 무료 AI(Gemini) 텍스트 추출 & 분석 함수 ---
# ==========================================
def get_real_ocr_text(image_url):
    if "GEMINI_API_KEY" not in st.secrets: return "Gemini API 키가 설정되지 않았습니다."
    try:
        res = requests.get(image_url)
        img = Image.open(io.BytesIO(res.content))
        
        # 💡 구글의 최신 무료 모델(2.5 Flash)로 이름 수정 완료!
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(["이 이미지에 적힌 텍스트를 모두 추출해줘. 요약하거나 다른 말을 덧붙이지 말고 원본 글자만 그대로 출력해줘.", img])
        return response.text
    except Exception as e:
        return f"텍스트 추출 실패: {e}"

def get_real_ai_advice(image_url, ticker):
    if "GEMINI_API_KEY" not in st.secrets: return "Gemini API 키가 설정되지 않았습니다."
    try:
        res = requests.get(image_url)
        img = Image.open(io.BytesIO(res.content))
        
        # 💡 구글의 최신 무료 모델(2.5 Flash)로 이름 수정 완료!
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"이 차트 이미지를 바탕으로 {ticker} 종목에 대한 전문적인 기술적 분석과 트레이딩 조언을 3~4줄로 핵심만 요약해줘."
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        return f"AI 분석 실패: {e}"

# --- 렌더링 도우미 ---
def render_blog_image_html(url):
    return f'<div style="width: 100%; display: flex; justify-content: center; margin-bottom: 5px;"><img src="{url}" style="max-width: 100%; max-height: 80vh; width: auto; height: auto; object-fit: contain; border: 1px solid #ddd; padding: 2px;" /></div>'

def render_crisp_image_html(url):
    return f'<div style="width: 100%; display: flex; justify-content: center; margin-bottom: 10px;"><img src="{url}" style="max-width: 100%; max-height: 80vh; width: auto; height: auto; object-fit: contain; image-rendering: crisp-edges; border: 2px solid #4a90e2; padding: 2px; box-shadow: 2px 2px 8px rgba(0,0,0,0.1);" /></div>'

def get_file_group_info(filename):
    name_without_ext = os.path.splitext(filename)[0]
    matches = re.findall(r'(\d+)(?:-(\d+))?', name_without_ext)
    if matches:
        last_match = matches[-1]
        return last_match[0], int(last_match[1] if last_match[1] else '0')
    return str(uuid.uuid4().hex[:4]), 0

# ==========================================
# --- 화면 구성 시작 ---
# ==========================================
st.set_page_config(page_title="나만의 트레이딩 대시보드", layout="wide")
st.title("📈 나만의 클라우드 매매 복기 & 자동 AI 분석 시스템")

st.markdown("""<style>div[data-testid="stInfo"] p { font-size: 1.1rem; } div[data-testid="stError"] p { font-size: 1.1rem; }</style>""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 매매 기록 보관지", "🔎 차트 분석 도구 (AI)", "📚 기본 이론 & DB", "📊 통계", "📁 분석 자료 아카이브"])

# --- Tab 1: 매매 기록 보관지 ---
with tab1:
    st.header("📝 매매 기록 보관지")
    df_trade = load_trade_data()
    
    with st.expander("➕ 새로운 매매 기록 추가하기", expanded=False):
        uploaded_images = st.file_uploader("차트 캡처 업로드", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key="trade_uploader")
        with st.form("trade_form", clear_on_submit=True):
            col1, col2, col3, col4 = st.columns(4)
            with col1: date = st.date_input("날짜", datetime.today())
            with col2: ticker = st.text_input("종목명 (예: BTC)").upper()
            with col3: timeframe = st.selectbox("타임프레임", ["1m", "5m", "15m", "1H", "4H", "1D"])
            with col4: setup_pattern = st.text_input("셋업/패턴")
            
            col5, col6, col7, col8 = st.columns(4)
            with col5: position = st.selectbox("포지션", ["Long", "Short"])
            with col6: result = st.selectbox("결과", ["승", "무", "패"])
            with col7: rr_ratio = st.text_input("손익비 (예: 1:2)")
            with col8: profit = st.number_input("수익금($)", step=1.0)
            
            st.divider()
            entry_basis = st.text_area("🟢 진입 근거", height=100)
            exit_basis = st.text_area("🔴 종료 근거", height=100)
            
            if st.form_submit_button("☁️ 클라우드에 기록 저장", type="primary", use_container_width=True):
                if not ticker: st.error("종목명을 입력해주세요!")
                else:
                    saved_urls = [upload_image_to_supabase(img, "trade") for img in (uploaded_images or [])]
                    saved_urls = [u for u in saved_urls if u]
                    insert_data = {"date": date.strftime("%Y-%m-%d"), "ticker": ticker, "timeframe": timeframe, "setup_pattern": setup_pattern, "position": position, "result": result, "rr_ratio": rr_ratio, "profit": profit, "chart_image_paths": "|".join(saved_urls), "entry_basis": entry_basis, "exit_basis": exit_basis}
                    insert_db("trade_history", insert_data)
                    st.success("성공적으로 저장되었습니다!")
                    st.rerun()

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
                    delete_db("trade_history", "id", trade_id)
                    st.rerun()
            
            c_chart, c_memo = st.columns([6, 4], gap="large")
            with c_chart:
                for u in str(trade_data.get("chart_image_paths", "")).split("|"):
                    if u: st.markdown(render_crisp_image_html(u), unsafe_allow_html=True)
            with c_memo:
                with st.form(f"edit_tr_{trade_id}"):
                    e_entry = st.text_area("🟢 진입 근거", value=trade_data.get("entry_basis", ""), height=150)
                    e_exit = st.text_area("🔴 종료 근거", value=trade_data.get("exit_basis", ""), height=150)
                    if st.form_submit_button("📝 내용 업데이트"):
                        update_db("trade_history", "id", trade_id, {"entry_basis": e_entry, "exit_basis": e_exit})
                        st.rerun()

with tab2: st.header("🔎 차트 분석 (준비중)")
with tab4: st.header("📊 통계 (준비중)")
with tab3: st.header("📚 이론 DB (준비중)")

# ==============================
# --- Tab 5: 분석 아카이브 (무료 Gemini 최신버전 연동!) ---
# ==============================
with tab5:
    st.header("📁 분석 자료 아카이브 (AI 자동화)")
    df_archive = load_archive_data()
    sub_tab_a, sub_tab_b = st.tabs(["👨‍🏫 타인 분석 스크랩", "👀 나의 관점 (Watchlist)"])
    
    with sub_tab_a:
        with st.expander("➕ 새로운 스크랩 추가하기", expanded=False):
            col_up1, col_up2 = st.columns(2)
            with col_up1:
                st.markdown("### 🖼️ 1. 포스팅 원본 (블로그/글 캡처)")
                arch_imgs_blog = st.file_uploader("인사이트 내용 캡처 (AI가 자동으로 텍스트 추출)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key="arch_imgs_blog", label_visibility="collapsed")
            with col_up2:
                st.markdown("### 🔍 2. 세부 고해상도 차트")
                arch_imgs_detail = st.file_uploader("고해상도 차트 (AI가 차트를 분석합니다)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key="arch_imgs_detail", label_visibility="collapsed")
            
            with st.form("archive_form_others", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)
                with col1: arch_date1 = st.date_input("스크랩 날짜", datetime.today())
                with col2: arch_ticker1 = st.text_input("종목명 (예: ETH)").upper()
                with col3: arch_source1 = st.text_input("출처 (예: 쉽알남 유튜브)")
                
                ai_advice_mapping = {}
                if arch_imgs_detail:
                    st.divider()
                    st.markdown("### 🤖 세부 차트 AI 조언 요청")
                    chart_names_for_ai = [f"{img_file.name}" for img_file in arch_imgs_detail]
                    selected_charts_for_ai = st.multiselect("AI 조언을 받을 차트(들)를 선택하세요.", chart_names_for_ai, default=chart_names_for_ai)
                
                if st.form_submit_button("☁️ 스크랩 & 무료 AI 분석 시작", use_container_width=True, type="primary"):
                    if not arch_ticker1: st.error("종목명을 입력해주세요!")
                    else:
                        with st.spinner("무료 AI(Gemini 최신버전)가 차트를 분석 중입니다... 잠시만 기다려주세요! 🤖"):
                            blog_urls, detail_urls = [], []
                            ai_advice_final_mapping, ocr_final_mapping = {}, {}
                            date_str = arch_date1.strftime("%Y-%m-%d")
                            
                            if arch_imgs_blog:
                                arch_imgs_blog = sorted(arch_imgs_blog, key=lambda x: int(get_file_group_info(x.name)[0]) if get_file_group_info(x.name)[0].isdigit() else 9999)
                                for img_file in arch_imgs_blog:
                                    group, sub = get_file_group_info(img_file.name)
                                    url = upload_image_to_supabase(img_file, f"arch_blog_{group}_{sub}")
                                    if url:
                                        blog_urls.append(url)
                                        ocr_final_mapping[group] = get_real_ocr_text(url)
                            
                            if arch_imgs_detail:
                                for img_file in arch_imgs_detail:
                                    group, sub = get_file_group_info(img_file.name)
                                    url = upload_image_to_supabase(img_file, f"arch_detail_{group}_{sub}")
                                    if url:
                                        detail_urls.append(url)
                                        if img_file.name in selected_charts_for_ai:
                                            ai_advice_final_mapping[group] = get_real_ai_advice(url, arch_ticker1)

                            insert_data = {
                                "date": date_str, "ticker": arch_ticker1, "category": "타인분석", "source_view": arch_source1,
                                "chart_image_paths": "|".join(blog_urls), "detail_image_paths": "|".join(detail_urls), "memo": "",
                                "ai_advice_mapping": json.dumps(ai_advice_final_mapping, ensure_ascii=False),
                                "ocr_text_mapping": json.dumps(ocr_final_mapping, ensure_ascii=False)
                            }
                            insert_db("analysis_archive", insert_data)
                        st.success("무료 AI 분석 및 클라우드 저장 완료!")
                        st.rerun()

        df_others = df_archive[df_archive['category'] == '타인분석'].copy()
        if not df_others.empty:
            st.markdown("### 📋 스크랩 목록")
            selected_other = st.dataframe(df_others[["date", "ticker", "source_view"]], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
            
            selected_rows_other = selected_other.get('selection', {}).get('rows', [])
            if selected_rows_other:
                st.divider()
                arch_data = df_others.iloc[selected_rows_other[0]]
                arch_id_current = arch_data['id']
                
                col_title, col_del = st.columns([8.5, 1.5])
                with col_title:
                    st.markdown(f"## 📚 {arch_data['date']} | {arch_data['ticker']} 분석 스크랩")
                    st.markdown(f"**출처:** {arch_data['source_view']}")
                with col_del:
                    if st.button("🗑️ 이 스크랩 삭제하기", type="primary", use_container_width=True):
                        delete_db("analysis_archive", "id", arch_id_current)
                        st.rerun()
                
                with st.expander("⚙️ 스크랩 기본 정보 수정", expanded=False):
                    with st.form(key=f"edit_basic_info_form_{arch_id_current}"):
                        c1, c2, c3 = st.columns(3)
                        with c1: new_date = st.date_input("날짜", value=pd.to_datetime(arch_data['date']).date())
                        with c2: new_ticker = st.text_input("종목명", value=arch_data['ticker'])
                        with c3: new_source = st.text_input("출처_관점", value=arch_data['source_view'])
                        if st.form_submit_button("정보 업데이트", use_container_width=True):
                            update_db("analysis_archive", "id", arch_id_current, {"date": new_date.strftime("%Y-%m-%d"), "ticker": new_ticker.upper(), "source_view": new_source})
                            st.rerun()
                st.write("")
                
                with st.form(key=f"edit_arch_memo_form_{arch_id_current}"):
                    st.markdown("### 📝 전체 핵심 요약 (나의 인사이트)")
                    edit_memo = st.text_area("배울 점 입력", value=arch_data.get("memo", ""), height=100)
                    if st.form_submit_button("인사이트 클라우드 저장", use_container_width=True):
                        update_db("analysis_archive", "id", arch_id_current, {"memo": edit_memo})
                        st.rerun()

                st.divider()
                st.markdown("### 📄 고해상도 차트 및 자동 AI 분석 결과")
                
                blog_path_str = arch_data.get("chart_image_paths", "")
                detail_path_str = arch_data.get("detail_image_paths", "")
                
                try: ai_advice_mapping = json.loads(arch_data.get("ai_advice_mapping", "{}"))
                except: ai_advice_mapping = {}
                try: ocr_mapping = json.loads(arch_data.get("ocr_text_mapping", "{}"))
                except: ocr_mapping = {}
                
                valid_blogs = [p for p in str(blog_path_str).split("|") if p]
                valid_details = [p for p in str(detail_path_str).split("|") if p]
                
                detail_dict = {}
                for dp in valid_details:
                    filename = dp.split('/')[-1]
                    if '_detail_' in filename:
                        parts = filename.split('_detail_')[1].split('_')
                        group = parts[0]
                        sub = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                        if group not in detail_dict: detail_dict[group] = []
                        detail_dict[group].append((sub, dp))

                for group in detail_dict: detail_dict[group] = [x[1] for x in sorted(detail_dict[group])]
                rendered_details = set()
                total_blogs = len(valid_blogs)

                if valid_blogs:
                    for idx, path in enumerate(valid_blogs):
                        current_blog_idx = idx + 1
                        filename = path.split('/')[-1]
                        group = filename.split('_blog_')[1].split('_')[0] if '_blog_' in filename else str(idx)
                        
                        matched_detail_paths = detail_dict.get(group, [])
                        badge_html = f"""<div style='margin-bottom: 8px;'><span style="background-color:#f0f2f6; padding:6px 12px; border-radius:6px; color:#333; font-weight:bold; font-size:15px; border: 1px solid #ddd;">📷 [ {current_blog_idx} / {total_blogs} ]</span></div>"""
                        
                        if matched_detail_paths:
                            rendered_details.update(matched_detail_paths)
                            state_key = f"show_blog_{arch_id_current}_{group}"
                            if state_key not in st.session_state: st.session_state[state_key] = False
                            show_blog = st.session_state[state_key]
                            num = group
                            
                            if show_blog:
                                c_blog, c_det, c_txt = st.columns([3.0, 5.5, 1.5], gap="medium")
                                with c_blog:
                                    st.markdown(badge_html, unsafe_allow_html=True)
                                    if st.button("❌ 원본 숨기기", key=f"close_btn_{state_key}", use_container_width=True):
                                        st.session_state[state_key] = False
                                        st.rerun()
                                    st.markdown(render_blog_image_html(path), unsafe_allow_html=True)
                                with c_det:
                                    for mdp in matched_detail_paths: st.markdown(render_crisp_image_html(mdp), unsafe_allow_html=True)
                                with c_txt:
                                    if num in ai_advice_mapping and ai_advice_mapping[num]: st.success(f"🤖 **{num}번 차트 AI 분석**\n\n{ai_advice_mapping[num]}")
                                    display_txt = ocr_mapping.get(num, "").strip()
                                    if display_txt: st.info(f"📄 **AI 텍스트 추출**\n\n{display_txt}")
                                    else: st.info(f"📄 **AI 텍스트 추출**\n\n*(추출된 텍스트가 없습니다.)*")
                                    with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                        with st.form(key=f"edit_ocr_open_{arch_id_current}_{num}"):
                                            edited_ocr = st.text_area("내용 교정", value=display_txt, height=150)
                                            if st.form_submit_button("클라우드 저장", use_container_width=True):
                                                ocr_mapping[num] = edited_ocr
                                                update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                                st.rerun()
                            else:
                                c_det, c_txt = st.columns([7.5, 2.5], gap="medium")
                                with c_det:
                                    for mdp in matched_detail_paths: st.markdown(render_crisp_image_html(mdp), unsafe_allow_html=True)
                                with c_txt:
                                    st.write("") 
                                    if st.button(f"🔍 [ {current_blog_idx} / {total_blogs} ] 원본 데이터 보기", key=f"open_btn_{state_key}", use_container_width=True):
                                        st.session_state[state_key] = True
                                        st.rerun()
                                    if num in ai_advice_mapping and ai_advice_mapping[num]: st.success(f"🤖 **{num}번 차트 AI 분석**\n\n{ai_advice_mapping[num]}")
                                    display_txt = ocr_mapping.get(num, "").strip()
                                    if display_txt: st.info(f"📄 **AI 텍스트 추출**\n\n{display_txt}")
                                    else: st.info(f"📄 **AI 텍스트 추출**\n\n*(추출된 텍스트가 없습니다.)*")
                                    with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                        with st.form(key=f"edit_ocr_closed_{arch_id_current}_{num}"):
                                            edited_ocr = st.text_area("내용 교정", value=display_txt, height=150)
                                            if st.form_submit_button("클라우드 저장", use_container_width=True):
                                                ocr_mapping[num] = edited_ocr
                                                update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                                st.rerun()
                        else:
                            c_blog, c_txt = st.columns([8.5, 1.5], gap="small")
                            num = group
                            with c_blog:
                                st.markdown(badge_html, unsafe_allow_html=True)
                                st.markdown(render_blog_image_html(path), unsafe_allow_html=True)
                            with c_txt:
                                if num in ai_advice_mapping and ai_advice_mapping[num]: st.success(f"🤖 **{num}번 차트 AI 분석**\n\n{ai_advice_mapping[num]}")
                                display_txt = ocr_mapping.get(num, "").strip()
                                if display_txt: st.info(f"📄 **AI 텍스트 추출**\n\n{display_txt}")
                                else: st.info(f"📄 **AI 텍스트 추출**\n\n*(추출된 텍스트가 없습니다.)*")
                                with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                    with st.form(key=f"edit_ocr_alone_{arch_id_current}_{num}"):
                                        edited_ocr = st.text_area("내용 교정", value=display_txt, height=150)
                                        if st.form_submit_button("클라우드 저장", use_container_width=True):
                                            ocr_mapping[num] = edited_ocr
                                            update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                            st.rerun()
                        st.markdown("<hr style='margin: 10px 0px; border: 0; border-top: 1px solid #eee;'>", unsafe_allow_html=True)
                else: st.info("저장된 포스팅 원본 이미지가 없습니다.")
                
                unrendered_details = [dp for dp in valid_details if dp not in rendered_details]
                if unrendered_details:
                    st.markdown("### 📎 기타 세부 차트")
                    for path in unrendered_details:
                        filename = path.split('/')[-1]
                        group = filename.split('_detail_')[1].split('_')[0] if '_detail_' in filename else "기타"
                        num = group
                        
                        c_u_img, c_u_txt = st.columns([7.5, 2.5], gap="medium")
                        with c_u_img: st.markdown(render_crisp_image_html(path), unsafe_allow_html=True)
                        with c_u_txt:
                            if num in ai_advice_mapping and ai_advice_mapping[num]: st.success(f"🤖 **{num}번 차트 조언**\n\n{ai_advice_mapping[num]}")
                            display_txt = ocr_mapping.get(num, "").strip()
                            if display_txt: st.info(f"📄 **AI 텍스트 추출**\n\n{display_txt}")
                            else: st.info(f"📄 **AI 텍스트 추출**\n\n*(추출된 텍스트가 없습니다.)*")
                            with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                with st.form(key=f"edit_ocr_other_{arch_id_current}_{num}"):
                                    edited_ocr = st.text_area("내용 교정", value=display_txt, height=150)
                                    if st.form_submit_button("클라우드 저장", use_container_width=True):
                                        ocr_mapping[num] = edited_ocr
                                        update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                        st.rerun()

    with sub_tab_b:
        st.write("나의 관점(Watchlist) 탭 역시 위와 동일한 구조로 작동합니다.")
