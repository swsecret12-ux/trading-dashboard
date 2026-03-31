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
        else:
            st.error("이미지 업로드 실패! 용량을 확인해주세요.")
            return None
    except Exception as e:
        return None

# ==========================================
# --- 3. 데이터 불러오기 함수들 ---
# ==========================================
def load_trade_data():
    res = requests.get(f"{URL}/rest/v1/trade_history?select=*&order=created_at.desc", headers=HEADERS)
    if res.status_code == 200 and res.json():
        return pd.DataFrame(res.json())
    return pd.DataFrame(columns=["id", "date", "ticker", "timeframe", "setup_pattern", "position", "result", "rr_ratio", "profit", "chart_image_paths", "entry_basis", "exit_basis"])

def load_archive_data():
    res = requests.get(f"{URL}/rest/v1/analysis_archive?select=*&order=created_at.desc", headers=HEADERS)
    if res.status_code == 200 and res.json():
        return pd.DataFrame(res.json())
    return pd.DataFrame(columns=["id", "date", "ticker", "category", "source_view", "chart_image_paths", "detail_image_paths", "memo"])

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

def render_crisp_image_html(url):
    return f'<div style="width: 100%; display: flex; justify-content: center; margin-bottom: 10px;"><img src="{url}" style="max-width: 100%; max-height: 80vh; width: auto; height: auto; object-fit: contain; border: 2px solid #4a90e2; padding: 2px; box-shadow: 2px 2px 8px rgba(0,0,0,0.1);" /></div>'

def render_blog_image_html(url):
    return f'<div style="width: 100%; display: flex; justify-content: center; margin-bottom: 5px;"><img src="{url}" style="max-width: 100%; max-height: 80vh; width: auto; height: auto; object-fit: contain; border: 1px solid #ddd; padding: 2px;" /></div>'

def get_file_group_info(filename):
    name_without_ext = os.path.splitext(filename)[0]
    matches = re.findall(r'(\d+)(?:-(\d+))?', name_without_ext)
    if matches:
        last_match = matches[-1]
        group = last_match[0] 
        sub = last_match[1] if last_match[1] else '0' 
        return group, int(sub)
    return str(uuid.uuid4().hex[:4]), 0

# ==========================================
# --- 화면 구성 시작 ---
# ==========================================
st.set_page_config(page_title="클라우드 트레이딩 대시보드", layout="wide")
st.title("☁️ 나만의 클라우드 매매 복기 & 분석 시스템")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 매매 기록 보관지", "🔎 차트 분석 (AI)", "📚 기본 이론 & DB", "📊 통계", "📁 분석 아카이브"])

# --- Tab 1 ~ 4 생략 (기존과 동일하게 유지) ---
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
                if not ticker: 
                    st.error("종목명을 입력해주세요!")
                else:
                    saved_urls = []
                    if uploaded_images:
                        for img in uploaded_images:
                            url = upload_image_to_supabase(img, "trade")
                            if url: saved_urls.append(url)
                            
                    insert_data = {
                        "date": date.strftime("%Y-%m-%d"),
                        "ticker": ticker,
                        "timeframe": timeframe,
                        "setup_pattern": setup_pattern,
                        "position": position,
                        "result": result,
                        "rr_ratio": rr_ratio,
                        "profit": profit,
                        "chart_image_paths": "|".join(saved_urls),
                        "entry_basis": entry_basis,
                        "exit_basis": exit_basis
                    }
                    res = insert_db("trade_history", insert_data)
                    if res.status_code in [200, 201]:
                        st.success("클라우드 DB에 성공적으로 저장되었습니다!")
                        st.rerun()
                    else:
                        st.error(f"저장 실패: {res.text}")

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

with tab3:
    st.header("📚 나의 매매 기준 & 기본 이론 DB")
    theory_db = load_theory_db()
    categories = list(theory_db.keys())
    
    col_menu, col_content = st.columns([3, 7], gap="large")
    with col_menu:
        selected_category = st.selectbox("카테고리 선택", categories + ["➕ 새 카테고리 추가하기"])
        if selected_category == "➕ 새 카테고리 추가하기":
            new_cat = st.text_input("새 카테고리명 입력")
            if st.button("카테고리 생성"): st.success("아래 폼에서 이론을 등록하면 카테고리가 생성됩니다!")
        else:
            titles = list(theory_db[selected_category].keys())
            selected_title = st.radio("세부 이론 선택", titles) if titles else None

        st.divider()
        with st.expander("📝 새로운 이론 등록하기", expanded=False):
            with st.form("add_theory_form", clear_on_submit=True):
                add_cat = st.selectbox("카테고리 지정", categories) if selected_category != "➕ 새 카테고리 추가하기" else new_cat
                add_title = st.text_input("이론 제목")
                add_content = st.text_area("상세 내용", height=150)
                add_imgs = st.file_uploader("참고 차트 업로드", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
                
                if st.form_submit_button("☁️ 클라우드 저장", type="primary"):
                    if add_title and add_content:
                        saved_img_urls = []
                        if add_imgs:
                            for img in add_imgs:
                                url = upload_image_to_supabase(img, "theory")
                                if url: saved_img_urls.append(url)
                        
                        update_db("theory_db", "title", add_title, {"content": add_content}) 
                        insert_data = {
                            "category": add_cat,
                            "title": add_title,
                            "content": add_content,
                            "image_paths": "|".join(saved_img_urls)
                        }
                        insert_db("theory_db", insert_data)
                        st.rerun()

    with col_content:
        if selected_category != "➕ 새 카테고리 추가하기" and selected_title:
            st.markdown(f"## 📖 {selected_title}")
            data = theory_db[selected_category][selected_title]
            st.markdown(data.get("content", ""))
            
            for url in data.get("images", []):
                if url: st.markdown(render_crisp_image_html(url), unsafe_allow_html=True)
            
            with st.expander("⚙️ 수정/삭제"):
                with st.form(f"edit_th_{selected_title}"):
                    edit_content = st.text_area("내용 수정", value=data.get("content", ""))
                    c_save, c_del = st.columns(2)
                    with c_save:
                        if st.form_submit_button("수정 저장"):
                            update_db("theory_db", "title", selected_title, {"content": edit_content})
                            st.rerun()
                    with c_del:
                        if st.form_submit_button("🗑️ 삭제"):
                            delete_db("theory_db", "title", selected_title)
                            st.rerun()

# ==============================
# --- Tab 5: 분석 아카이브 (매핑 복구 완료!) ---
# ==============================
with tab5:
    st.header("📁 분석 자료 아카이브")
    df_archive = load_archive_data()
    
    with st.expander("➕ 새로운 스크랩 추가하기", expanded=False):
        c_up1, c_up2 = st.columns(2)
        with c_up1: arch_imgs_blog = st.file_uploader("포스팅 원본", type=['png', 'jpg'], accept_multiple_files=True, key="up_blog")
        with c_up2: arch_imgs_detail = st.file_uploader("세부 차트", type=['png', 'jpg'], accept_multiple_files=True, key="up_detail")
        
        with st.form("arch_form"):
            c1, c2, c3 = st.columns(3)
            with c1: arch_date = st.date_input("날짜", datetime.today())
            with c2: arch_ticker = st.text_input("종목명").upper()
            with c3: arch_source = st.text_input("출처")
            
            if st.form_submit_button("☁️ 스크랩 클라우드 저장", type="primary", use_container_width=True):
                blog_urls, detail_urls = [], []
                if arch_imgs_blog:
                    for img in arch_imgs_blog:
                        group, sub = get_file_group_info(img.name)
                        url = upload_image_to_supabase(img, f"arch_blog_{group}_{sub}")
                        if url: blog_urls.append(url)
                if arch_imgs_detail:
                    for img in arch_imgs_detail:
                        group, sub = get_file_group_info(img.name)
                        url = upload_image_to_supabase(img, f"arch_detail_{group}_{sub}")
                        if url: detail_urls.append(url)
                        
                insert_data = {
                    "date": arch_date.strftime("%Y-%m-%d"),
                    "ticker": arch_ticker,
                    "category": "타인분석",
                    "source_view": arch_source,
                    "chart_image_paths": "|".join(blog_urls),
                    "detail_image_paths": "|".join(detail_urls)
                }
                insert_db("analysis_archive", insert_data)
                st.success("클라우드 DB에 스크랩 완료!")
                st.rerun()

    if not df_archive.empty:
        df_others = df_archive[df_archive['category'] == '타인분석']
        st.markdown("### 📋 스크랩 목록")
        sel_arch = st.dataframe(df_others[["date", "ticker", "source_view"]], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        
        if sel_arch.get('selection', {}).get('rows', []):
            st.divider()
            arch_data = df_others.iloc[sel_arch['selection']['rows'][0]]
            arch_id = arch_data['id']
            
            c_t, c_d = st.columns([8.5, 1.5])
            with c_t: st.markdown(f"## 📚 {arch_data['date']} | {arch_data['ticker']} ({arch_data['source_view']})")
            with c_d:
                if st.button("🗑️ 삭제", type="primary", use_container_width=True, key=f"del_ar_{arch_id}"):
                    delete_db("analysis_archive", "id", arch_id)
                    st.rerun()
            
            # 클라우드 저장된 URL들을 파싱해서 다시 그룹핑하는 로직
            blog_paths = [u for u in str(arch_data.get("chart_image_paths", "")).split("|") if u]
            detail_paths = [u for u in str(arch_data.get("detail_image_paths", "")).split("|") if u]
            
            grouped_data = {}
            
            for url in blog_paths:
                match = re.search(r'arch_blog_(\w+)_', url)
                group = match.group(1) if match else "기타"
                if group not in grouped_data: grouped_data[group] = {"blog": [], "detail": []}
                grouped_data[group]["blog"].append(url)
                
            for url in detail_paths:
                match = re.search(r'arch_detail_(\w+)_', url)
                group = match.group(1) if match else "기타"
                if group not in grouped_data: grouped_data[group] = {"blog": [], "detail": []}
                grouped_data[group]["detail"].append(url)

            # 매핑된 그룹별로 예쁘게 화면에 출력!
            for group, urls in sorted(grouped_data.items(), key=lambda x: str(x[0])):
                st.markdown(f"### 📌 [세트 {group}] 원본 및 세부 차트")
                
                for b_url in urls["blog"]:
                    st.markdown(render_blog_image_html(b_url), unsafe_allow_html=True)
                
                if urls["detail"]:
                    cols = st.columns(len(urls["detail"]))
                    for idx, d_url in enumerate(urls["detail"]):
                        with cols[idx]:
                            st.markdown(render_crisp_image_html(d_url), unsafe_allow_html=True)
                st.divider()
