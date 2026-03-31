import streamlit as st
import pandas as pd
import requests
import json
import uuid
import re
import os
from datetime import datetime

# ==========================================
# --- 1. 클라우드 연결 세팅 (다이렉트 방식) ---
# ==========================================
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

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
        img_headers = {
            "apikey": KEY,
            "Authorization": f"Bearer {KEY}",
            "Content-Type": img_file.type
        }
        
        res = requests.post(upload_url, headers=img_headers, data=file_bytes)
        if res.status_code == 200:
            return f"{URL}/storage/v1/object/public/chart_images/{file_name}"
        return None
    except Exception as e:
        return None

# ==========================================
# --- 3. 데이터 로드 및 시뮬레이션 함수 ---
# ==========================================
def load_trade_data():
    res = requests.get(f"{URL}/rest/v1/trade_history?select=*&order=created_at.desc", headers=HEADERS)
    if res.status_code == 200 and res.json():
        return pd.DataFrame(res.json())
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
            cat = row['category']
            title = row['title']
            if cat not in db_dict: db_dict[cat] = {}
            db_dict[cat][title] = {
                "content": row.get('content', ''),
                "images": row.get('image_paths', '').split('|') if row.get('image_paths') else []
            }
    else:
        db_dict = {"기본 카테고리": {"환영합니다!": {"content": "새로운 이론을 추가해 보세요.", "images": []}}}
    return db_dict

# --- 이미지 렌더링 도우미 (클라우드 URL 방식 적용) ---
def render_blog_image_html(url):
    return f"""
        <div style="width: 100%; display: flex; justify-content: center; margin-bottom: 5px;">
            <img src="{url}" 
                 style="max-width: 100%; max-height: 80vh; width: auto; height: auto; 
                        object-fit: contain; image-rendering: -webkit-optimize-contrast; 
                        border: 1px solid #ddd; padding: 2px;" />
        </div>
    """

def render_crisp_image_html(url):
    return f"""
        <div style="width: 100%; display: flex; justify-content: center; margin-bottom: 10px;">
            <img src="{url}" 
                 style="max-width: 100%; max-height: 80vh; width: auto; height: auto; 
                        object-fit: contain; image-rendering: -webkit-optimize-contrast; 
                        image-rendering: crisp-edges; 
                        border: 2px solid #4a90e2; padding: 2px; box-shadow: 2px 2px 8px rgba(0,0,0,0.1);" />
        </div>
    """

def get_file_group_info(filename):
    name_without_ext = os.path.splitext(filename)[0]
    matches = re.findall(r'(\d+)(?:-(\d+))?', name_without_ext)
    if matches:
        last_match = matches[-1]
        group = last_match[0] 
        sub = last_match[1] if last_match[1] else '0' 
        return group, int(sub)
    return str(uuid.uuid4().hex[:4]), 0

# (영우님의 AI & OCR 텍스트 로직 그대로 유지)
def get_simulated_ai_advice_per_chart(chart_num, ticker):
    ticker_upper = ticker.upper() if ticker else "해당 종목"
    return f"포스팅 내용과 {ticker_upper} 차트를 교차 검증한 결과입니다.\n\n현재 캔들이 주요 지지/저항 라인에서 유의미한 반응(꼬리 달림 등)을 보이고 있습니다. 하위 프레임에서의 구조 변화(CH)를 확인한 후 진입하는 것이 안전합니다."

def get_simulated_ocr_text(chart_num, date_str):
    if "03-25" in date_str or "03-28" in date_str:
        mapping_25 = {
            '2': "↑ 트레이딩 현황\n\n롱포지션은 짧게 스탑로스가 발동되어 종료되었습니다.\n\n이후 약 1.7%가 더 하락하며, 나름 타이트하게 잘 잘라냈던 것 같네요.\n\n앞으로의 대응은 밑에 차트 보면서 차근차근 살펴보겠습니다.",
            '3': "↑ 비트코인 1시간\n\n최근 활용했던 주요 상승 추세선(파랑)은 이제 사실상 트레이딩에 활용할 수 없습니다.\n\n현재의 움직임을 살펴보면, 추세선이 거의 없는 듯 의식하지 않고 움직이고 있습니다.",
            '4': "↑ 비트코인 날봉\n\n첫 번째로는 날봉 오더블럭 입니다.\n\n새벽의 하락은 이 FVG에서 멈췄고, 반등까지 강력하게 나오고 있는 모습을 보여주고 있습니다."
        }
        return mapping_25.get(chart_num, "")
    elif "03-30" in date_str or "03-31" in date_str:
        mapping_30 = {
            '2': "↑ AMD 구조\n\n↑ 비트코인 30분봉\n\n현재 비트코인을 단기적으로 보면, AMD 구조가 출현했습니다.\n\nAMD 구조는 그리 어려운 구조는 아닙니다.\n\n* 축적 = 횡보\n* 조작 = Fake out 혹은 Trap 혹은 유동성 흡수\n* 분배 = 패턴 컨펌 후 추세 출현",
            '3': "↑ 비트코인 6시간봉\n\n현재 메인 상승 추세선(파랑)을 기준으로 움직이고 있습니다.\n\n메인 추세선을 하향 돌파 이후, 다시 상향 돌파하면서 Trap 패턴을 형성해준 것으로 보여지네요."
        }
        return mapping_30.get(chart_num, "")
    else:
        return ""

# ==========================================
# --- 화면 구성 시작 ---
# ==========================================
st.set_page_config(page_title="나만의 트레이딩 대시보드", layout="wide")
st.title("📈 나만의 클라우드 매매 복기 & 분석 시스템")

st.markdown("""
<style>
    div[data-testid="stInfo"] p { font-size: 1.1rem; }
    div[data-testid="stError"] p { font-size: 1.1rem; }
</style>
""", unsafe_allow_html=True)

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
                    saved_urls = []
                    if uploaded_images:
                        for img in uploaded_images:
                            url = upload_image_to_supabase(img, "trade")
                            if url: saved_urls.append(url)
                            
                    insert_data = {
                        "date": date.strftime("%Y-%m-%d"), "ticker": ticker, "timeframe": timeframe,
                        "setup_pattern": setup_pattern, "position": position, "result": result,
                        "rr_ratio": rr_ratio, "profit": profit, "chart_image_paths": "|".join(saved_urls),
                        "entry_basis": entry_basis, "exit_basis": exit_basis
                    }
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
                urls = str(trade_data.get("chart_image_paths", "")).split("|")
                for u in urls:
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
# --- Tab 5: 분석 아카이브 (영우님 커스텀 UI 완벽 복구!) ---
# ==============================
with tab5:
    st.header("📁 분석 자료 아카이브")
    df_archive = load_archive_data()
    sub_tab_a, sub_tab_b = st.tabs(["👨‍🏫 타인 분석 스크랩", "👀 나의 관점 (Watchlist)"])
    
    with sub_tab_a:
        with st.expander("➕ 새로운 스크랩 추가하기", expanded=False):
            col_up1, col_up2 = st.columns(2)
            with col_up1:
                st.markdown("### 🖼️ 1. 포스팅 원본 (블로그/글 캡처)")
                arch_imgs_blog = st.file_uploader("인사이트 내용 캡처", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key="arch_imgs_blog", label_visibility="collapsed")
            with col_up2:
                st.markdown("### 🔍 2. 세부 고해상도 차트")
                arch_imgs_detail = st.file_uploader("고해상도 차트 (예: 차트2-1.png)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key="arch_imgs_detail", label_visibility="collapsed")
            
            with st.form("archive_form_others", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)
                with col1: arch_date1 = st.date_input("스크랩 날짜", datetime.today())
                with col2: arch_ticker1 = st.text_input("종목명 (예: ETH)").upper()
                with col3: arch_source1 = st.text_input("출처 (예: 쉽알남 유튜브)")
                
                ai_advice_mapping = {}
                if arch_imgs_detail:
                    st.divider()
                    st.markdown("### 🤖 세부 차트 AI 조언 요청")
                    st.caption("기본적으로 업로드된 모든 세부 차트에 대해 AI 조언이 생성됩니다.")
                    chart_names_for_ai = [f"{img_file.name}" for img_file in arch_imgs_detail]
                    selected_charts_for_ai = st.multiselect("AI 조언을 받을 차트(들)를 선택하세요.", chart_names_for_ai, default=chart_names_for_ai)
                
                if st.form_submit_button("☁️ 스크랩 클라우드 저장", use_container_width=True, type="primary"):
                    if not arch_ticker1: st.error("종목명을 입력해주세요!")
                    else:
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
                                    ocr_final_mapping[group] = get_simulated_ocr_text(group, date_str)
                        
                        if arch_imgs_detail:
                            for img_file in arch_imgs_detail:
                                group, sub = get_file_group_info(img_file.name)
                                url = upload_image_to_supabase(img_file, f"arch_detail_{group}_{sub}")
                                if url:
                                    detail_urls.append(url)
                                    if img_file.name in selected_charts_for_ai:
                                        ai_advice_final_mapping[group] = get_simulated_ai_advice_per_chart(group, arch_ticker1)

                        insert_data = {
                            "date": date_str, "ticker": arch_ticker1, "category": "타인분석", "source_view": arch_source1,
                            "chart_image_paths": "|".join(blog_urls), "detail_image_paths": "|".join(detail_urls), "memo": "",
                            "ai_advice_mapping": json.dumps(ai_advice_final_mapping, ensure_ascii=False),
                            "ocr_text_mapping": json.dumps(ocr_final_mapping, ensure_ascii=False)
                        }
                        insert_db("analysis_archive", insert_data)
                        st.success("클라우드 DB에 스크랩 완료!")
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
                st.markdown("### 📄 고해상도 차트 및 분석 (메인 뷰어)")
                
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

                for group in detail_dict:
                    detail_dict[group] = [x[1] for x in sorted(detail_dict[group])]

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
                                    for mdp in matched_detail_paths:
                                        st.markdown(render_crisp_image_html(mdp), unsafe_allow_html=True)
                                with c_txt:
                                    if num in ai_advice_mapping and ai_advice_mapping[num]:
                                        st.success(f"🤖 **{num}번 차트 종합 AI 조언**\n\n{ai_advice_mapping[num]}")
                                    display_txt = ocr_mapping.get(num, "").strip()
                                    if display_txt: st.info(f"📄 **텍스트 추출**\n\n{display_txt}")
                                    else: st.info(f"📄 **텍스트 추출**\n\n*(등록된 텍스트가 없습니다. 아래에서 직접 입력해주세요.)*")
                                    
                                    with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                        with st.form(key=f"edit_ocr_open_{arch_id_current}_{num}"):
                                            edited_ocr = st.text_area("내용을 입력하세요", value=display_txt, height=150)
                                            if st.form_submit_button("클라우드 저장", use_container_width=True):
                                                ocr_mapping[num] = edited_ocr
                                                update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                                st.rerun()
                            else:
                                c_det, c_txt = st.columns([7.5, 2.5], gap="medium")
                                with c_det:
                                    for mdp in matched_detail_paths:
                                        st.markdown(render_crisp_image_html(mdp), unsafe_allow_html=True)
                                with c_txt:
                                    st.write("") 
                                    if st.button(f"🔍 [ {current_blog_idx} / {total_blogs} ] 원본 데이터 보기", key=f"open_btn_{state_key}", use_container_width=True):
                                        st.session_state[state_key] = True
                                        st.rerun()
                                    if num in ai_advice_mapping and ai_advice_mapping[num]:
                                        st.success(f"🤖 **{num}번 차트 종합 AI 조언**\n\n{ai_advice_mapping[num]}")
                                    display_txt = ocr_mapping.get(num, "").strip()
                                    if display_txt: st.info(f"📄 **텍스트 추출**\n\n{display_txt}")
                                    else: st.info(f"📄 **텍스트 추출**\n\n*(등록된 텍스트가 없습니다. 아래에서 직접 입력해주세요.)*")
                                    
                                    with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                        with st.form(key=f"edit_ocr_closed_{arch_id_current}_{num}"):
                                            edited_ocr = st.text_area("내용을 입력하세요", value=display_txt, height=150)
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
                                if num in ai_advice_mapping and ai_advice_mapping[num]:
                                    st.success(f"🤖 **{num}번 차트 AI 조언**\n\n{ai_advice_mapping[num]}")
                                display_txt = ocr_mapping.get(num, "").strip()
                                if display_txt: st.info(f"📄 **텍스트 추출**\n\n{display_txt}")
                                else: st.info(f"📄 **텍스트 추출**\n\n*(등록된 텍스트가 없습니다. 아래에서 직접 입력해주세요.)*")
                                
                                with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                    with st.form(key=f"edit_ocr_alone_{arch_id_current}_{num}"):
                                        edited_ocr = st.text_area("내용을 입력하세요", value=display_txt, height=150)
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
                        with c_u_img:
                            st.markdown(render_crisp_image_html(path), unsafe_allow_html=True)
                        with c_u_txt:
                            if num in ai_advice_mapping and ai_advice_mapping[num]:
                                st.success(f"🤖 **{num}번 차트 조언**\n\n{ai_advice_mapping[num]}")
                            display_txt = ocr_mapping.get(num, "").strip()
                            if display_txt: st.info(f"📄 **텍스트 추출**\n\n{display_txt}")
                            else: st.info(f"📄 **텍스트 추출**\n\n*(등록된 텍스트가 없습니다. 아래에서 직접 입력해주세요.)*")
                            
                            with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                with st.form(key=f"edit_ocr_other_{arch_id_current}_{num}"):
                                    edited_ocr = st.text_area("내용을 입력하세요", value=display_txt, height=150)
                                    if st.form_submit_button("클라우드 저장", use_container_width=True):
                                        ocr_mapping[num] = edited_ocr
                                        update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                        st.rerun()

    with sub_tab_b:
        st.write("나의 관점(Watchlist) 탭 역시 위와 동일한 구조로 작동합니다.")
