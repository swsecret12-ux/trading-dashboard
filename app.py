import streamlit as st
import pandas as pd
import requests
import json
import uuid
import re
import os
import io
import time
import ccxt
from datetime import datetime
from PIL import Image
import google.generativeai as genai
import streamlit.components.v1 as components

# ==========================================
# --- 1. 클라우드 및 AI 세팅 ---
# ==========================================
URL = st.secrets.get("SUPABASE_URL", "")
KEY = st.secrets.get("SUPABASE_KEY", "")
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

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
        
        if not file_bytes: return None
            
        upload_url = f"{URL}/storage/v1/object/chart_images/{file_name}"
        img_headers = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": getattr(img_file, 'type', 'image/png')}
        
        res = requests.post(upload_url, headers=img_headers, data=file_bytes)
        if res.status_code == 200:
            return f"{URL}/storage/v1/object/public/chart_images/{file_name}"
        return None
    except Exception:
        return None

# ==========================================
# --- 3. 데이터 로드 함수 및 아카이브 컨텍스트 추출 ---
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

def get_recent_archive_context(ticker_search):
    df = load_archive_data()
    if df.empty or not ticker_search: return ""
    
    recent_scraps = df[(df['ticker'].str.contains(ticker_search, case=False, na=False, regex=False)) & (df['category'] == '타인분석')].head(3)
    if recent_scraps.empty: return ""
    
    context = "[최근 아카이브 참조 데이터 (원작자/전문가 관점)]\n"
    for _, row in recent_scraps.iterrows():
        context += f"- 날짜: {row['date']} | 출처: {row['source_view']}\n"
        context += f"  내용 요약(AI메모): {row['memo']}\n"
        try:
            ocr_map = json.loads(row['ocr_text_mapping']) if isinstance(row['ocr_text_mapping'], str) else row['ocr_text_mapping']
            if ocr_map and isinstance(ocr_map, dict) and len(ocr_map) > 0:
                first_ocr = list(ocr_map.values())[0][:300] 
                context += f"  원작자 본문 일부: {first_ocr}...\n"
        except:
            pass
    return context

def load_sector_data():
    res = requests.get(f"{URL}/rest/v1/sector_analysis?select=*&order=created_at.desc", headers=HEADERS)
    if res.status_code == 200 and res.json(): return pd.DataFrame(res.json())
    return pd.DataFrame(columns=["id", "ticker", "sector", "market_cap", "vol_1d", "vol_1w", "vol_1m", "vol_1q", "vol_1y", "issue", "detail_data", "ai_analysis"])

# 여기서부터 로컬 모듈 임포트
from api_utils import (
    get_gemini_keys, parse_ai_json, ask_gemini_dynamic, get_real_ocr_text, 
    get_real_ai_advice, render_ai_advice_block, render_blog_image_html, 
    render_crisp_image_html, get_file_group_info, execute_survival_trade, load_theory_db
)
from market_research import fetch_financial_data, analyze_sector_with_ai, fetch_saveticker_news

st.set_page_config(page_title="나만의 트레이딩 대시보드", layout="wide")

st.markdown("""
<style>
div[data-testid="stInfo"] p { font-size: 1.1rem; } 
div[data-testid="stError"] p { font-size: 1.1rem; }

div[data-testid="stMetricValue"] {
    font-size: 1.2rem !important;
}
div[data-testid="stMetricLabel"] {
    font-size: 0.85rem !important;
    color: #666;
}

.info-card {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 25px;
    margin-bottom: 25px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}
.info-card h4 {
    color: #1e40af;
    margin-top: 0;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 12px;
    font-size: 1.3rem;
}

/* 💡 표(Table) 가독성 극대화 CSS */
.ma-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 15px;
    font-size: 1.05rem; /* 글씨 크기 대폭 확대 */
}
.ma-table th, .ma-table td {
    border: 1px solid #cbd5e1;
    padding: 12px 15px; /* 여백 확대 */
    text-align: left;
}
.ma-table th {
    background-color: #e2e8f0;
    font-weight: bold;
    color: #1e293b;
    text-align: center;
}
.ma-table tr:nth-child(even) {
    background-color: #f8fafc;
}
.ma-table tr:hover {
    background-color: #f1f5f9;
}

@media (max-width: 768px) {
    .block-container {
        padding-top: 2rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-bottom: 2rem !important;
    }
    h1 { font-size: 1.8rem !important; }
    h2 { font-size: 1.5rem !important; }
    h3 { font-size: 1.2rem !important; }
    p, span, div { font-size: 1rem !important; }
    button[data-baseweb="tab"] {
        font-size: 0.9rem !important;
        padding-left: 10px !important;
        padding-right: 10px !important;
    }
}
</style>
""", unsafe_allow_html=True)

st.title("📈 나만의 클라우드 매매 복기 & 자동 AI 분석 시스템")

if "ai_analysis_done" not in st.session_state:
    st.session_state.ai_analysis_done = False
    st.session_state.ai_result = ""
    st.session_state.ai_view_text = ""
    st.session_state.ai_img_files = [] 

if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0 

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📝 매매 기록 보관지", "🔎 AI 차트 & 관점 분석", "📚 기본 이론 & DB", "🤖 자동매매 사령실", "📁 분석 자료 아카이브", "🏢 섹터 & 주도주 맵"])

# --- Tab 1: 매매 기록 보관지 ---
with tab1:
    st.header("📝 매매 기록 보관지")
    df_trade = load_trade_data()
    if not df_trade.empty:
        df_trade = df_trade.sort_values(by='date', ascending=False).reset_index(drop=True)
    
    with st.expander("➕ 새로운 매매 기록 추가하기", expanded=True):
        uploaded_images = st.file_uploader("차트 캡처 업로드", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key="trade_uploader")
        
        # 💡 직관적인 UI 1: 기본 정보 그룹화
        st.markdown("#### 📝 1. 기본 정보")
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns(4)
            with col1: date = st.date_input("날짜", datetime.today())
            with col2: ticker = st.text_input("종목명 (예: BTC)").upper()
            with col3: timeframe = st.selectbox("타임프레임", ["1m", "5m", "15m", "1H", "4H", "1D"])
            with col4: setup_pattern = st.text_input("셋업/패턴")
            
        # 💡 직관적인 UI 2: 포지션 및 수익 자동 계산
        st.markdown("#### 💰 2. 포지션 및 수익 계산")
        with st.container(border=True):
            col5, col6, col7, col8, col9 = st.columns(5)
            with col5: position = st.selectbox("포지션", ["Long", "Short"])
            with col6: leverage = st.number_input("레버리지 (x)", min_value=1, value=10, step=1)
            with col7: margin = st.number_input("투자 원금 ($)", min_value=0.0, value=1000.0, step=100.0)
            with col8: entry_price = st.number_input("진입 가격", min_value=0.0, value=0.0, format="%.4f")
            with col9: exit_price = st.number_input("종료 가격", min_value=0.0, value=0.0, format="%.4f")
            
            # 실시간 수익금 계산 로직
            profit_calc = 0.0
            if entry_price > 0 and exit_price > 0:
                if position == "Long":
                    profit_calc = ((exit_price - entry_price) / entry_price) * margin * leverage
                else:
                    profit_calc = ((entry_price - exit_price) / entry_price) * margin * leverage
            
            # 결과 자동 판독
            if profit_calc > 0: auto_res = "승"
            elif profit_calc < 0: auto_res = "패"
            else: auto_res = "무"
            
            st.info(f"**💡 자동 계산된 수익금:** `${profit_calc:,.2f}` &nbsp;&nbsp;|&nbsp;&nbsp; **ROE (수익률):** `{profit_calc/margin*100 if margin>0 else 0:,.2f}%`")
            
        # 💡 직관적인 UI 3: 결과 및 근거
        st.markdown("#### 📊 3. 결과 및 근거")
        with st.container(border=True):
            col10, col11 = st.columns(2)
            # 입력된 가격이 있으면 자동으로 승/무/패 세팅
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
                
                # 입력된 포지션 정보를 근거 텍스트에 자동으로 덧붙여서 영구 보존
                detailed_entry = f"[진입가: {entry_price} | 레버리지: {leverage}x | 원금: ${margin}]\n{entry_basis}"
                detailed_exit = f"[종료가: {exit_price}]\n{exit_basis}"
                
                insert_data = {
                    "date": date.strftime("%Y-%m-%d"), 
                    "ticker": ticker, 
                    "timeframe": timeframe, 
                    "setup_pattern": setup_pattern, 
                    "position": position, 
                    "result": result, 
                    "rr_ratio": rr_ratio, 
                    "profit": round(profit_calc, 2), # 자동 계산된 수익금 저장
                    "chart_image_paths": "|".join(saved_urls), 
                    "entry_basis": detailed_entry, 
                    "exit_basis": detailed_exit
                }
                insert_db("trade_history", insert_data)
                st.success("성공적으로 저장되었습니다!")
                time.sleep(1)
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

# ==============================
# --- Tab 2: 내 관점 분석 (아카이브 연동 & 매크로 뉴스) ---
# ==============================
with tab2:
    st.header("🔍 AI 차트 분석 및 관점 피드백 (아카이브 지식 연동)")
    st.info("차트 스크린샷을 올리면, 아카이브(Tab 5)에 저장된 해당 종목의 최신 전문가 관점을 스스로 찾아내어 함께 분석합니다.")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        view_uploaded_files = st.file_uploader("📷 차트 이미지 업로드 (여러 장 드래그 가능)", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="view_uploader")
        if view_uploaded_files:
            for img in view_uploaded_files:
                st.image(img, caption=img.name, use_container_width=True)
            
    with col2:
        ticker_input = st.text_input("분석할 티커 입력 (예: BTC, NDX)").upper()
        user_view = st.text_area("✍️ 현재 나의 관점 (예: 1시간봉 전저점 스윕 확인, 롱 진입 대기중)", height=100)
        
        if st.button("🚀 아카이브 기반 AI 관점 분석 요청", type="primary", use_container_width=True):
            keys = get_gemini_keys()
            if not keys:
                st.error("Gemini API 키가 설정되지 않았습니다. (Settings -> Secrets에 추가해주세요)")
            elif view_uploaded_files and ticker_input:
                with st.spinner('아카이브에서 관련 자료를 찾고 분석하는 중... 🤖'):
                    try:
                        archive_context = get_recent_archive_context(ticker_input)
                        
                        img_bytes_list = []
                        img_objs = []
                        for f in view_uploaded_files:
                            b = f.getvalue()
                            img_bytes_list.append({"bytes": b, "name": f.name, "type": getattr(f, 'type', 'image/png')})
                            img_objs.append(Image.open(io.BytesIO(b)))
                        
                        analysis_prompt = f"""
                        당신은 월스트리트 출신의 전문 트레이더이자 나의 트레이딩 멘토입니다. 
                        내가 첨부한 차트 이미지(멀티 타임프레임)와 아래의 [나의 관점]을 종합적으로 검토해 주세요.
                        
                        [종목]: {ticker_input}
                        [나의 관점]: {user_view}
                        
                        {archive_context}
                        
                        **[중요 분석 지침]**
                        1. **아카이브 동기화**: 위 [최근 아카이브 참조 데이터]가 있다면, 거기에 기록된 원작자의 최신 포지션(롱/숏)과 근거를 최우선으로 참고하세요.
                        2. **언급 시점 대조**: 원작자가 근거를 제시한 '시간'과 '가격 레벨'이 현재 차트에서 어떻게 구현되고 있는지 팩트 체크하세요.
                        3. **가장 먼저**, 첨부된 차트 이미지 상단이나 텍스트를 보고 1) 어떤 종목(티커)인지 2) 몇 시간(분) 봉(타임프레임)인지 파악해서 분석의 첫 문장에 명확히 명시해 주세요. (이미지에서 알 수 없는 경우 '타임프레임 파악 불가'로 기재)
                        4. **분석 결과 필수 포함**: analysis 항목에는 반드시 "아카이브에 기록된 원작자가 O시에 말한 OOO 근거에 따르면 현재는 OOO한 상태입니다"라는 식으로 언급 시점과 근거를 명시해서 현재 나의 관점을 검증해야 합니다.

                        반드시 아래의 JSON 형식으로만 답변을 출력해. 마크다운(` ```json ` 등)이나 다른 인사말은 절대 포함하지 마. 오직 중괄호 {{ }} 만 출력해.
                        
                        {{
                          "trend": "상승 / 하락 / 횡보 등 10자 이내 요약",
                          "key_level": "핵심 지지/저항 15자 이내 요약",
                          "momentum": "모멘텀 상태 15자 이내 요약",
                          "volume": "거래량 상태 10자 이내 요약",
                          "s_score": "0~4 사이의 정수 (유동성, 오더블록, 지지저항, 패턴 중첩 개수)",
                          "macro_news": "차트상 급등/급락이 관찰될 경우, 연관될 수 있는 매크로 이슈(나스닥 커플링, 경제지표 발표, 뉴스 등)를 추론하여 1~2줄로 요약. 특이 흐름이 없으면 '특이 동향 없음' 기재.",
                          "analysis": "1) 종목/타임프레임 명시. 2) 아카이브 근거 기반 팩트폭행 및 조언 3~4줄."
                        }}
                        """
                        analysis_result = ask_gemini_dynamic(analysis_prompt, img_objs)
                        
                        st.session_state.ai_analysis_done = True
                        st.session_state.ai_result = analysis_result
                        st.session_state.ai_view_text = user_view
                        st.session_state.ai_img_files = img_bytes_list
                        
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"분석 중 오류가 발생했습니다: {e}")
            else:
                st.warning("⚠️ 차트 이미지를 1장 이상 업로드하고 '분석할 티커'를 반드시 입력해 주세요.")

    if st.session_state.ai_analysis_done:
        st.success("✅ 아카이브 연동 AI 분석 완료!")
        render_ai_advice_block("🤖 AI 멘토의 정밀 피드백", st.session_state.ai_result)
        
        st.divider()
        with st.expander("💾 이 관점을 '나의 관점(Watchlist)'에 저장하기", expanded=True):
            st.info("종목명만 확인하시면 Tab 5의 관점 아카이브로 여러 장의 차트와 피드백이 영구 저장됩니다.")
            with st.form("save_watchlist_form"):
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    w_ticker = st.text_input("종목명 (예: BTCUSDT)", value=ticker_input).upper()
                with col_w2:
                    w_date = st.date_input("저장 날짜", datetime.today())
                
                if st.form_submit_button("🚀 나의 관점(Watchlist)에 저장", type="primary", use_container_width=True):
                    if not w_ticker:
                        st.error("종목명을 입력해주세요!")
                    else:
                        with st.spinner("클라우드에 안전하게 보관 중입니다..."):
                            class DummyFile:
                                def __init__(self, b, n, t):
                                    self.b = b
                                    self.name = n
                                    self.type = t
                                def getvalue(self):
                                    return self.b
                            
                            saved_urls = []
                            for file_data in st.session_state.ai_img_files:
                                dummy_img = DummyFile(file_data['bytes'], file_data['name'], file_data['type'])
                                img_url = upload_image_to_supabase(dummy_img, "watchlist")
                                if img_url:
                                    saved_urls.append(img_url)
                                    
                            final_urls_str = "|".join(saved_urls)
                            
                            insert_data = {
                                "date": w_date.strftime("%Y-%m-%d"), 
                                "ticker": w_ticker, 
                                "category": "나의관점", 
                                "source_view": st.session_state.ai_view_text,
                                "chart_image_paths": final_urls_str, 
                                "detail_image_paths": "", 
                                "memo": st.session_state.ai_result, 
                                "ai_advice_mapping": "{}",
                                "ocr_text_mapping": "{}"
                            }
                            insert_db("analysis_archive", insert_data)
                            
                            st.session_state.ai_analysis_done = False
                            st.session_state.ai_img_files = [] 
                            st.success("✅ Watchlist에 성공적으로 저장되었습니다! [📁 분석 자료 아카이브] 탭에서 확인하세요.")
                            st.rerun()

# ==============================
# --- Tab 3: 기본 이론 & DB ---
# ==============================
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
                st.caption("기존에 있는 목차와 똑같은 '카테고리'와 '이론 제목'을 입력하면 내용이 클라우드에 영구 저장(덮어쓰기) 됩니다.")
                target_cat = sel_cat if sel_cat != "➕ 새 카테고리 추가" else new_cat_name
                th_title = st.text_input("이론 제목 (목차 이름과 동일하게 입력)")
                th_cont = st.text_area("상세 내용", height=200)
                th_imgs = st.file_uploader("참고 차트 업로드 (선택)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
                if st.form_submit_button("☁️ 클라우드 저장", type="primary"):
                    if th_title and th_cont:
                        img_urls = [upload_image_to_supabase(i, "theory") for i in (th_imgs or [])]
                        img_urls = [u for u in img_urls if u] 
                        insert_db("theory_db", {
                            "category": target_cat,
                            "title": th_title,
                            "content": th_cont,
                            "image_paths": "|".join(img_urls)
                        })
                        st.rerun()
                    else:
                        st.error("제목과 내용을 모두 입력해주세요.")

    with col_r:
        if sel_title and theory_db[sel_cat][sel_title].get("id") is not None:
            data = theory_db[sel_cat][sel_title]
            st.markdown(f"## 📖 {sel_title}")
            st.caption(f"분류: {sel_cat}")
            st.divider()

            st.markdown(data['content'])

            if data['images']:
                st.markdown("<br>### 🖼️ 참고 차트 캡처", unsafe_allow_html=True)
                for u in data['images']:
                    if u: st.markdown(render_crisp_image_html(u), unsafe_allow_html=True)

            st.write("")
            
            if data['id'] != "default":
                with st.expander("⚙️ 이 내용 수정 / 삭제하기", expanded=False):
                    with st.form(f"ed_th_{data['id']}"):
                        ed_cont = st.text_area("내용 수정", value=data['content'], height=250)
                        c_s, c_d = st.columns([7, 3])
                        if c_s.form_submit_button("📝 수정 내용 저장", type="primary", use_container_width=True):
                            update_db("theory_db", "id", data['id'], {"content": ed_cont})
                            st.rerun()
                        if c_d.form_submit_button("🗑️ 이 이론 삭제", use_container_width=True):
                            delete_db("theory_db", "id", data['id'])
                            st.rerun()
            else:
                st.info("💡 위 내용은 시스템에 내장된 '기본 뼈대(예정본)'입니다. 좌측 하단의 '새로운 이론 등록'을 통해 같은 이름으로 내용을 저장하시면 클라우드 DB에 영구 기록되어 차트 첨부 및 자유로운 수정이 가능해집니다!")
        else:
            st.info("👈 왼쪽 목차에서 이론을 선택하시거나, 하단의 '새로운 이론 등록/덮어쓰기'를 통해 나만의 매매 기준을 채워나가 보세요!")

# ==============================
# --- Tab 4: 🤖 자동매매 컨트롤 센터 ---
# ==============================
with tab4:
    st.header("🤖 자동매매 사령실 (컨트롤 패널)")
    st.caption("비트겟(Bitget) API 연동 반자동 생존 매매 및 트레이딩뷰 Webhook 시스템")
    st.write("")

    st.markdown("### 📊 현재 봇 상태")
    col_status1, col_status2, col_status3, col_status4 = st.columns(4)
    
    with col_status1:
        bot_on = st.toggle("🚀 봇 가동 스위치 (마스터)", value=False)
        st.markdown(f"**시스템 상태:** {'🟢 작동 중 (Running)' if bot_on else '🔴 대기 중 (Standby)'}")
    with col_status2:
        st.metric("오늘의 예상 수익", "+$0.00", "0.0%")
    with col_status3:
        st.metric("승률 (최근 10건)", "0.0%", "-")
    with col_status4:
        st.metric("현재 포지션", "대기 중 (Flat)", "")

    st.divider()

    bot_tab1, bot_tab2, bot_tab3, bot_tab4 = st.tabs(["⚙️ 기본 세팅 (API)", "🛡️ 반자동 생존 매매", "🧠 매매 전략 & 웹훅", "📋 실시간 작동 로그"])

    with bot_tab1:
        st.subheader("🔑 거래소 연결 및 자금 관리")
        with st.form("bot_basic_form", border=True):
            st.info("발급받은 비트겟(Bitget) API Key를 입력하세요.")
            c1, c2 = st.columns(2)
            with c1:
                api_key = st.text_input("Bitget API Key (Access Key)", type="password", value=st.session_state.get('bg_api', ''))
                secret_key = st.text_input("Bitget Secret Key", type="password", value=st.session_state.get('bg_secret', ''))
            with c2:
                api_passphrase = st.text_input("API Passphrase (비밀번호)", type="password", value=st.session_state.get('bg_pass', ''))
                risk_limit = st.slider("1회 진입 시 허용 리스크 (총 시드의 %)", min_value=0.1, max_value=5.0, value=1.0, step=0.1, help="이 비율만큼만 잃도록 진입 수량을 자동 조절합니다.")

            if st.form_submit_button("기본 세팅 및 세션 저장", type="primary"):
                st.session_state['bg_api'] = api_key
                st.session_state['bg_secret'] = secret_key
                st.session_state['bg_pass'] = api_passphrase
                st.session_state['bg_risk'] = risk_limit
                st.success("API 및 자금 세팅이 활성화되었습니다! 이제 생존 매매 탭을 이용할 수 일습니다.")

    with bot_tab2:
        st.subheader("🛡️ 반자동 생존 매매 (기계적 손절)")
        st.markdown("**'손절은 패배가 아닌 필수 생존법입니다.'** 진입과 동시에 스탑로스가 API를 통해 서버에 꽂힙니다.")
        
        with st.form("survival_trade_form"):
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1: sv_symbol = st.text_input("종목명 (예: BTC/USDT:USDT)", value="BTC/USDT:USDT")
            with col_s2: sv_side = st.selectbox("포지션 방향", ["buy (Long)", "sell (Short)"])
            with col_s3: sv_sl_percent = st.number_input("손절 비율 (%)", min_value=0.1, max_value=10.0, value=2.0, step=0.1)
            
            sv_reason = st.text_area("📝 진입 근거 (매매 일지에 자동 기록됩니다)", placeholder="예: 1시간봉 주요 유동성 스윕 확인 후 진입")
            
            submit_trade = st.form_submit_button("🚀 진입 및 스탑로스 자동 세팅", type="primary", use_container_width=True)
            
            if submit_trade:
                if not st.session_state.get('bg_api'):
                    st.error("⚠️ 먼저 [기본 세팅 (API)] 탭에서 API 키를 저장해주세요.")
                else:
                    with st.spinner("비트겟 서버로 주문을 전송하는 중입니다..."):
                        real_side = "buy" if "buy" in sv_side else "sell"
                        success, message = execute_survival_trade(
                            st.session_state['bg_api'], 
                            st.session_state['bg_secret'], 
                            st.session_state['bg_pass'],
                            sv_symbol, 
                            real_side, 
                            sv_sl_percent, 
                            sv_reason, 
                            st.session_state.get('bg_risk', 1.0)
                        )
                        if success: st.success(message)
                        else: st.error(message)

    with bot_tab3:
        st.subheader("🎯 트레이딩뷰 연동 (Webhook) 설정")
        c_hook, c_strat = st.columns([6, 4], gap="large")
        
        with c_hook:
            st.markdown("👇 **트레이딩뷰 얼러트(Alert) 창에 넣을 Webhook URL**")
            st.code("[https://youngwoo-trading.streamlit.app/api/webhook](https://youngwoo-trading.streamlit.app/api/webhook)", language="text")
            st.markdown("👇 **트레이딩뷰 메시지 양식 (예시)**")
            st.code('{\n  "action": "long",\n  "ticker": "BTCUSDT",\n  "strategy": "OrderBlock"\n}', language="json")
            
        with c_strat:
            st.selectbox("메인 전략 선택", ["트레이딩뷰 알람(Webhook) 전용", "AI 차트 감시 결합형 (베타)"])
            st.checkbox("손절(SL) 도달 시 즉시 시장가 종료 (안전장치)", value=True)
            st.checkbox("반대 신호 발생 시 기존 포지션 스위칭", value=False)
            if st.button("전략 저장", use_container_width=True):
                st.success("전략이 업데이트 되었습니다.")

    with bot_tab4:
        st.subheader("📡 로봇 작동 터미널")
        st.caption("최근 50개의 시스템 로그를 보여줍니다.")
        log_text = """[System] 컨트롤 패널이 정상적으로 활성화되었습니다.
[System] Bitget API 키 대기 중...
[System] 봇 가동 시 이 터미널에 매매 내역이 기록됩니다.
[System] 생존 매매 모듈 활성화 완료..."""
        st.code(log_text, language="bash")

# ==============================
# --- Tab 5: 분석 자료 아카이브 ---
# ==============================
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

# ==============================
# --- Tab 6: 🏢 섹터 & 주도주 리서치 맵 ---
# ==============================
with tab6:
    st.header("🏢 섹터 & 주도주 맵 (AI 리서치 저장소)")
    st.info("야후 파이낸스(yfinance)를 통해 4H/1D 이평선 크로스, 실적, 최신 뉴스를 긁어오고 AI가 심층 리포트를 작성합니다.")
    
    with st.expander("➕ 새 종목 리서치 자동화 추가하기"):
        with st.form("new_sector_stock"):
            c1, c2 = st.columns(2)
            s_ticker = c1.text_input("야후 파이낸스 티커 (예: NVDA, AAPL, SNOW)")
            s_sector = c2.selectbox("섹터 분류", ["AI", "소프트웨어", "반도체", "조선", "헬스케어", "코인", "기타"])
            
            s_issue = st.text_area("🔥 내가 주목하는 핵심 이슈 (나만의 투자 관점)", height=100)
            
            if st.form_submit_button("🤖 금융 데이터 자동 긁어오기 & AI 리서치 시작", type="primary"):
                if s_ticker:
                    # 영우님의 SaveTicker 계정 하드코딩
                    st_id = "swsecret@naver.com"
                    st_pw = "1!REre4423"
                    
                    with st.spinner("데이터 수집 및 크로스체크 심층 분석 중... (매크로 환경 분석으로 인해 1~2분 소요됩니다)"):
                        fin_data = fetch_financial_data(s_ticker.strip())
                        st_news_content = fetch_saveticker_news(st_id, st_pw)
                        
                        if "error" in fin_data: st.error(f"데이터 수집 실패: {fin_data['error']}")
                        else:
                            ai_res = analyze_sector_with_ai(s_ticker, s_sector, fin_data, s_issue, st_news_content)
                            
                            # 💡 좌측 패널 HTML 구성 (실적표, 이평선, 모멘텀 포함)
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
            
        # 💡 메인 화면 목록 (EMA 표기 변경)
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
            
            # 💡 트레이딩뷰 위젯에 EMA(지수이동평균) 2개 기본 탑재!
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
              "studies": ["Moving Average Exponential@tv-basicstudies", "Moving Average Exponential@tv-basicstudies"],
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
