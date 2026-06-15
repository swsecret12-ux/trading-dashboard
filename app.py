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
import altair as alt
from datetime import datetime, timezone, timedelta
from PIL import Image
import google.generativeai as genai
import streamlit.components.v1 as components
import yfinance as yf

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

def insert_db(table, data): return requests.post(f"{URL}/rest/v1/{table}", headers=HEADERS, json=data)
def update_db(table, match_col, match_val, data): return requests.patch(f"{URL}/rest/v1/{table}?{match_col}=eq.{match_val}", headers=HEADERS, json=data)
def delete_db(table, match_col, match_val): return requests.delete(f"{URL}/rest/v1/{table}?{match_col}=eq.{match_val}", headers=HEADERS)

def upload_image_to_supabase(img_file, prefix="img"):
    try:
        file_ext = img_file.name.split('.')[-1]
        file_name = f"{prefix}_{uuid.uuid4().hex[:8]}.{file_ext}"
        file_bytes = img_file.getvalue()
        if not file_bytes: return None
        upload_url = f"{URL}/storage/v1/object/chart_images/{file_name}"
        img_headers = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": getattr(img_file, 'type', 'image/png')}
        res = requests.post(upload_url, headers=img_headers, data=file_bytes)
        if res.status_code == 200: return f"{URL}/storage/v1/object/public/chart_images/{file_name}"
        return None
    except Exception: return None

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
                context += f"  원작자 본문 일부: {list(ocr_map.values())[0][:300]}...\n"
        except: pass
    return context

def load_sector_data():
    res = requests.get(f"{URL}/rest/v1/sector_analysis?select=*&order=created_at.desc", headers=HEADERS)
    if res.status_code == 200 and res.json(): return pd.DataFrame(res.json())
    return pd.DataFrame(columns=["id", "ticker", "sector", "market_cap", "vol_1d", "vol_1w", "vol_1m", "vol_1q", "vol_1y", "issue", "detail_data", "ai_analysis"])

def format_mcap_krw(usd_val):
    try:
        val = float(usd_val)
        if val <= 0: return "-"
        krw_val = val * 1380
        if krw_val >= 1e12: # 조 단위
            trillion = krw_val / 1e12
            # 1조 미만의 단위를 억으로 환산하여 표현 (예: 1.3조 -> 1조 3,000억원)
            t_part = int(trillion)
            b_part = int((trillion - t_part) * 10000)
            if t_part == 0: return f"{b_part:,}억원"
            if b_part == 0: return f"{t_part:,}조원"
            return f"{t_part:,}조 {b_part:,}억원"
        elif krw_val >= 1e8: # 억 단위
            billion = krw_val / 1e8
            return f"{int(billion):,}억원"
        return "-"
    except:
        return usd_val

SECTOR_TRANSLATIONS = {
    "Technology Services": "Information Technology (정보기술)",
    "Electronic Technology": "Information Technology (정보기술)",
    "Health Technology": "Health Care (헬스케어)",
    "Health Services": "Health Care (헬스케어)",
    "Finance": "Financials (금융)",
    "Consumer Non-Durables": "Consumer Staples (필수소비재)",
    "Consumer Durables": "Consumer Discretionary (자유소비재)",
    "Consumer Services": "Consumer Discretionary (자유소비재)",
    "Retail Trade": "Consumer Discretionary (자유소비재)",
    "Energy Minerals": "Energy (에너지)",
    "Non-Energy Minerals": "Materials (소재)",
    "Producer Manufacturing": "Industrials (산업재)",
    "Industrial Services": "Industrials (산업재)",
    "Transportation": "Industrials (산업재)",
    "Utilities": "Utilities (유틸리티)",
    "Communications": "Communication Services (커뮤니케이션)",
    "Commercial Services": "Communication Services (커뮤니케이션)"
}

NAME_TRANSLATIONS = {
    "AAPL": "Apple Inc. (애플)", "MSFT": "Microsoft (마이크로소프트)", "NVDA": "NVIDIA (엔비디아)",
    "GOOGL": "Alphabet Class A (구글)", "GOOG": "Alphabet Class C (구글)", "AMZN": "Amazon (아마존)",
    "META": "Meta Platforms (메타/페이스북)", "BRK.B": "Berkshire Hathaway (버크셔)", "LLY": "Eli Lilly (일라이 릴리)",
    "TSLA": "Tesla (테슬라)", "AVGO": "Broadcom (브로드컴)", "V": "Visa (비자)",
    "JPM": "JPMorgan Chase (JP모건)", "WMT": "Walmart (월마트)", "UNH": "UnitedHealth (유나이티드헬스)",
    "MA": "Mastercard (마스터카드)", "PG": "Procter & Gamble (P&G)", "JNJ": "Johnson & Johnson (존슨앤드존슨)",
    "HD": "Home Depot (홈디포)", "COST": "Costco (코스트코)", "MRK": "Merck & Co. (머크)",
    "ABBV": "AbbVie (애브비)", "CRM": "Salesforce (세일즈포스)", "AMD": "Advanced Micro Devices (AMD)",
    "NFLX": "Netflix (넷플릭스)", "KO": "Coca-Cola (코카콜라)", "PEP": "PepsiCo (펩시코)",
    "DIS": "Walt Disney (디즈니)", "CSCO": "Cisco Systems (시스코)", "ADBE": "Adobe (어도비)",
    "QCOM": "Qualcomm (퀄컴)", "INTC": "Intel (인텔)", "ARM": "ARM Holdings (암 홀딩스)",
    "PLTR": "Palantir (팔란티어)", "RTX": "RTX Corporation (레이시온)", "PFE": "Pfizer (화이자)"
}

def get_robust_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })
    return session

@st.cache_data(ttl=3600)
def get_nasdaq_performance():
    try:
        ndx = yf.Ticker("^IXIC").history(period="4y")
        curr = ndx['Close'].iloc[-1]
        def ret(days):
            if len(ndx) > days: return (curr - ndx['Close'].iloc[-(days+1)]) / ndx['Close'].iloc[-(days+1)] * 100
            return 0
        return {"1일": ret(1), "7일": ret(5), "1개월": ret(21), "3개월": ret(63), "6개월": ret(126), "1년": ret(252), "3년": ret(756)}
    except: return {}

from api_utils import (
    get_gemini_keys, parse_ai_json, ask_gemini_dynamic, get_real_ocr_text, 
    get_real_ai_advice, render_ai_advice_block, render_blog_image_html, 
    render_crisp_image_html, get_file_group_info, execute_survival_trade, load_theory_db
)
from market_research import fetch_financial_data, analyze_sector_with_ai

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

if "ai_analysis_done" not in st.session_state:
    st.session_state.ai_analysis_done = False
    st.session_state.ai_result = ""
    st.session_state.ai_view_text = ""
    st.session_state.ai_img_files = [] 
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0 
if "sp100_state_df" not in st.session_state:
    st.session_state.sp100_state_df = pd.DataFrame()

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

with tab2:
    st.header("🔍 AI 차트 분석 및 관점 피드백 (아카이브 지식 연동)")
    st.info("차트 스크린샷을 올리면, 아카이브(Tab 5)에 저장된 해당 종목의 최신 전문가 관점을 스스로 찾아내어 함께 분석합니다.")
    col1, col2 = st.columns([1, 1])
    with col1:
        view_uploaded_files = st.file_uploader("📷 차트 이미지 업로드 (여러 장 드래그 가능)", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="view_uploader")
        if view_uploaded_files:
            for img in view_uploaded_files: st.image(img, caption=img.name, use_container_width=True)
    with col2:
        ticker_input = st.text_input("분석할 티커 입력 (예: BTC, NDX)").upper()
        user_view = st.text_area("✍️ 현재 나의 관점 (예: 1시간봉 전저점 스윕 확인, 롱 진입 대기중)", height=100)
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
                        당신은 월스트리트 출신의 전문 트레이더입니다. 
                        [종목]: {ticker_input}
                        [나의 관점]: {user_view}
                        {archive_context}
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

with tab4:
    st.header("🤖 자동매매 사령실 (컨트롤 패널)")
    col_status1, col_status2, col_status3, col_status4 = st.columns(4)
    with col_status1:
        bot_on = st.toggle("🚀 봇 가동 스위치 (마스터)", value=False)
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
        st.code("[https://youngwoo-trading.streamlit.app/api/webhook](https://youngwoo-trading.streamlit.app/api/webhook)", language="text")
    with bot_tab4:
        st.code("[System] 봇 모듈 준비 완료...", language="bash")

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
                if st.form_submit_button("저장", type="primary"):
                    insert_db("analysis_archive", {
                        "date": arch_date1.strftime("%Y-%m-%d"), "ticker": arch_ticker1, "category": "타인분석", 
                        "source_view": arch_source1, "chart_image_paths": "", "detail_image_paths": "", "memo": "",
                        "ai_advice_mapping": "{}", "ocr_text_mapping": "{}"
                    })
                    st.rerun()

        df_others = df_archive[df_archive['category'] == '타인분석'].copy()
        if not df_others.empty:
            df_others = df_others.sort_values(by='date', ascending=False).reset_index(drop=True)
            selected_other = st.dataframe(df_others[["date", "ticker", "source_view"]], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
            if selected_other.get('selection', {}).get('rows', []):
                arch_id_current = df_others.iloc[selected_other['selection']['rows'][0]]['id']
                if st.button("🗑️ 삭제", key=f"del_arch_{arch_id_current}"):
                    delete_db("analysis_archive", "id", arch_id_current); st.rerun()

    with sub_tab_b:
        st.markdown("### 👀 나의 관점 (Watchlist)")

with tab6:
    st.header("🏢 섹터 & 주도주 맵 (AI 리서치 저장소)")
    st.info("야후 파이낸스(yfinance)를 통해 4H/1D 이평선 크로스, 실적, 최신 뉴스를 긁어오고 AI가 심층 리포트를 작성합니다.")
    
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
                                    <div class='info-card'><h4>🔥 나의 투자 관점</h4><p>{s_issue}</p></div>
                                    """
                                    insert_db("sector_analysis", {
                                        "ticker": s_ticker.upper(), "sector": s_sector, "market_cap": fin_data.get('market_cap', 0),
                                        "vol_1d": fin_data.get('last_cross_type', '-'), "vol_1w": fin_data.get('last_cross_date', '-'), 
                                        "vol_1m": "", "vol_1q": "", "vol_1y": "",
                                        "issue": left_column_html, "detail_data": fin_data.get('raw_news', ''), "ai_analysis": ai_res
                                    })
                                    st.success("리서치 리포트 등록 완료!"); time.sleep(1); st.rerun()
                            except Exception as e:
                                st.error(f"분석 중 치명적 오류 발생: {str(e)}")

        df_sector = load_sector_data()
        if not df_sector.empty:
            filter_sec = st.selectbox("섹터 필터링", ["전체"] + list(df_sector['sector'].unique()))
            if filter_sec != "전체": df_sector = df_sector[df_sector['sector'] == filter_sec]
                
            # 리서치 탭 테이블 렌더링 시 시가총액을 format_mcap_krw로 즉시 변환
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
                    if st.button("🗑️ 삭제", type="primary", use_container_width=True): delete_db("sector_analysis", "id", s_id); st.rerun()
                
                # 💡 트레이딩뷰 위젯: EMA (MAExp) + RSI 적용
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
                    with st.expander("📰 구글 기반 글로벌 핵심 뉴스 (파트너십, 실적 등)", expanded=False):
                        st.write(stock_data.get('detail_data', '수집된 뉴스가 없습니다.'))
                with c_right:
                    if stock_data.get('ai_analysis'):
                        st.markdown("#### 🤖 AI 월스트리트 애널리스트 심층 리포트")
                        st.markdown(stock_data['ai_analysis'], unsafe_allow_html=True)

    with sub_tab_top100:
        st.markdown("### 🇺🇸 미국 시총 상위 Top 100 기업 (실시간 데이터 기준)")
        st.info("💡 **알림:** 하드코딩된 명단이 아닙니다! **[실시간 스캔 시작]** 버튼을 누르면, 트레이딩뷰(TradingView) 라이브 서버에서 테슬라, ARM, 팔란티어 등을 포함한 '진짜 실시간 미국 시가총액 1위~100위' 명단을 즉시 스캔하여 줄을 세웁니다.")

        if st.button("🔄 실시간 순수 미국 시총 Top 100 스캔 시작", type="primary"):
            with st.spinner("미국 시장 전 종목을 스캔하여 실시간 시총 100위를 선별 중입니다... (약 2초 소요)"):
                try:
                    url = "https://scanner.tradingview.com/america/scan"
                    payload = {
                        "filter": [
                            {"left": "market_cap_basic", "operation": "nempty"},
                            {"left": "type", "operation": "in_range", "right": ["stock", "dr"]}
                        ],
                        "options": {"lang": "en"},
                        "markets": ["america"],
                        "symbols": {"query": {"types": []}, "tickers": []},
                        "columns": ["name", "description", "sector", "market_cap_basic"],
                        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                        "range": [0, 100]
                    }
                    headers = {"User-Agent": "Mozilla/5.0"}
                    res = requests.post(url, json=payload, headers=headers)
                    data = res.json()
                    
                    df_list = []
                    for i, item in enumerate(data.get('data', [])):
                        sym = item['d'][0].replace('.', '-')
                        name_raw = item['d'][1]
                        sec_raw = item['d'][2]
                        mcap = item['d'][3]
                        
                        sec_trans = SECTOR_TRANSLATIONS.get(sec_raw, f"{sec_raw} (기타)")
                        name_trans = NAME_TRANSLATIONS.get(sym, name_raw)
                        
                        df_list.append({
                            '순위': i + 1,
                            '시총': format_mcap_krw(mcap),
                            'Symbol': sym,
                            'Name': name_trans,
                            'Sector': sec_trans,
                            '시가총액_num': mcap,
                            '섹터 순위': "-",
                            '크로스 상태 (4H/1D EMA200)': "대기 중",
                            '크로스 날짜': "-",
                            '크로스 당시 주가': "-",
                            '업데이트 날짜': "-"
                        })
                    
                    new_df = pd.DataFrame(df_list)
                    new_df['섹터 내 순위'] = new_df.groupby('Sector')['시가총액_num'].rank(ascending=False, method='min')
                    new_df['섹터 순위'] = new_df['섹터 내 순위'].apply(lambda x: f"섹터 {int(x)}위" if pd.notna(x) else "-")
                    new_df = new_df.drop(columns=['섹터 내 순위'])
                    
                    st.session_state.sp100_state_df = new_df
                    st.success("✅ 실시간 미국 시총 Top 100 리스트 업데이트 완료!")
                except Exception as e:
                    st.error(f"데이터 스캔 중 오류가 발생했습니다: {e}")

        if not st.session_state.sp100_state_df.empty:
            col_pie, col_ndx = st.columns([6, 4], gap="large")
            
            with col_pie:
                st.markdown("#### 🍩 미국 주도 섹터 비중 (스캔된 종목 기준)")
                c_p1, c_p2 = st.columns(2)
                
                with c_p1:
                    sector_count = st.session_state.sp100_state_df['Sector'].value_counts().reset_index()
                    sector_count.columns = ['Sector', 'Count']
                    sector_count['Percentage'] = (sector_count['Count'] / sector_count['Count'].sum() * 100).round(1).astype(str) + '%'
                    sector_count['LegendLabel'] = sector_count['Sector'] + " (" + sector_count['Percentage'] + ")"
                    
                    fig_count = alt.Chart(sector_count).mark_arc(innerRadius=45).encode(
                        theta=alt.Theta(field="Count", type="quantitative"),
                        color=alt.Color(field="LegendLabel", type="nominal", legend=alt.Legend(title="섹터 (종목 수)", orient="bottom", columns=1, labelLimit=500)),
                        tooltip=['Sector', alt.Tooltip('Count', title="포함 종목 수"), alt.Tooltip('Percentage', title="비중")]
                    ).properties(title="[종목 개수 기준]", height=450)
                    st.altair_chart(fig_count, use_container_width=True)
                
                with c_p2:
                    sector_mcap = st.session_state.sp100_state_df.groupby('Sector')['시가총액_num'].sum().reset_index()
                    total_mcap = sector_mcap['시가총액_num'].sum()
                    sector_mcap['Percentage'] = (sector_mcap['시가총액_num'] / total_mcap * 100).round(1).astype(str) + '%'
                    sector_mcap['Formatted_Mcap'] = sector_mcap['시가총액_num'].apply(format_mcap_krw)
                    sector_mcap['LegendLabel'] = sector_mcap['Sector'] + " (" + sector_mcap['Percentage'] + ")"
                    
                    fig_mcap = alt.Chart(sector_mcap).mark_arc(innerRadius=45).encode(
                        theta=alt.Theta(field="시가총액_num", type="quantitative"),
                        color=alt.Color(field="LegendLabel", type="nominal", legend=alt.Legend(title="섹터 (시총 합산)", orient="bottom", columns=1, labelLimit=500)),
                        tooltip=['Sector', alt.Tooltip('Formatted_Mcap', title="시가총액 합산"), alt.Tooltip('Percentage', title="비중")]
                    ).properties(title="[종합 시가총액 기준]", height=450)
                    st.altair_chart(fig_mcap, use_container_width=True)
            
            with col_ndx:
                st.markdown("#### 📈 나스닥(^IXIC) 기간별 수익률 지표")
                ndx_data = get_nasdaq_performance()
                if ndx_data:
                    ndx_df = pd.DataFrame([ndx_data])
                    def color_val(val):
                        color = '#ef4444' if val < 0 else '#22c55e'
                        return f"color: {color}; font-weight: bold;"
                    formatted_df = ndx_df.map(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)
                    st.dataframe(formatted_df.style.map(lambda x: color_val(float(x.strip('%')))), use_container_width=True, hide_index=True)
                    
                    st.markdown("#### 📊 나스닥 최근 1년 흐름 (주봉 선 차트)")
                    ndx_tv_widget = """
                    <div class="tradingview-widget-container" style="height:320px;width:100%;">
                      <div id="tradingview_ixic" style="height:calc(100% - 32px);width:100%"></div>
                      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                      <script type="text/javascript">
                      new TradingView.widget({
                      "autosize": true, "symbol": "OANDA:NAS100USD", "interval": "W", "timezone": "Etc/UTC",
                      "theme": "light", "style": "3", "locale": "kr", "enable_publishing": false,
                      "hide_top_toolbar": true, "hide_legend": true, "save_image": false,
                      "container_id": "tradingview_ixic"
                      });
                      </script>
                    </div>
                    """
                    components.html(ndx_tv_widget, height=320)
                else:
                    st.write("나스닥 데이터를 불러오는 중입니다...")

            st.markdown("---")

            symbols = st.session_state.sp100_state_df['Symbol'].tolist()
            chunks = [symbols[i:i+25] for i in range(0, 100, 25)]
            labels = ["1위~25위", "26위~50위", "51위~75위", "76위~100위"]
            
            st.caption("야후 파이낸스 데이터 차단(Rate Limit)을 방지하기 위해 25개 종목씩 나누어 '4시간봉 EMA 200 vs 1일봉 EMA 200' 크로스 현황을 정밀 스캔합니다.")
            cols = st.columns(4)
            for i in range(4):
                if i < len(chunks):
                    if cols[i].button(f"🚀 {labels[i]} 스캔", use_container_width=True):
                        with st.spinner(f"{labels[i]} 실시간 시총 및 크로스 데이터 스캔 중... (약 5초)"):
                            try:
                                session = get_robust_session()
                                data_1d_raw = yf.download(chunks[i], period="2y", interval="1d", progress=False)
                                data_1h_raw = yf.download(chunks[i], period="730d", interval="1h", progress=False)
                                
                                if 'Close' in data_1d_raw: data_1d = data_1d_raw['Close']
                                else: data_1d = data_1d_raw
                                    
                                if 'Close' in data_1h_raw: data_1h = data_1h_raw['Close']
                                else: data_1h = data_1h_raw
                                    
                                if isinstance(data_1d, pd.Series): data_1d = data_1d.to_frame(name=chunks[i][0])
                                if isinstance(data_1h, pd.Series): data_1h = data_1h.to_frame(name=chunks[i][0])
                                
                                current_update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                
                                for sym in chunks[i]:
                                    if sym not in data_1d.columns or sym not in data_1h.columns:
                                        c_type, c_date, c_price = "데이터 부족", "-", "-"
                                    else:
                                        df_sym_1d = data_1d[sym].dropna()
                                        df_sym_1h = data_1h[sym].dropna()
                                        
                                        if len(df_sym_1d) < 150 or len(df_sym_1h) < 150:
                                            c_type, c_date, c_price = "상장기간 부족", "-", "-"
                                        else:
                                            df_1d_ma = pd.DataFrame({'Close': df_sym_1d})
                                            df_1d_ma['EMA200_1D'] = df_1d_ma['Close'].ewm(span=200, adjust=False).mean()
                                            
                                            df_1h_ma = pd.DataFrame({'Close': df_sym_1h})
                                            df_4h_ma = df_1h_ma.resample('4h').agg({'Close': 'last'}).dropna()
                                            df_4h_ma['EMA200_4H'] = df_4h_ma['Close'].ewm(span=200, adjust=False).mean()
                                            
                                            df_1d_ma.index = pd.to_datetime(df_1d_ma.index, utc=True)
                                            df_4h_ma.index = pd.to_datetime(df_4h_ma.index, utc=True)
                                            
                                            df_1d_ma = df_1d_ma[['EMA200_1D']].sort_index()
                                            df_4h_ma = df_4h_ma[['EMA200_4H', 'Close']].sort_index()
                                            
                                            merged = pd.merge_asof(df_4h_ma, df_1d_ma, left_index=True, right_index=True, direction='backward').dropna()
                                            merged['Prev_4H'] = merged['EMA200_4H'].shift(1)
                                            merged['Prev_1D'] = merged['EMA200_1D'].shift(1)
                                            
                                            gc = merged[(merged['EMA200_4H'] > merged['EMA200_1D']) & (merged['Prev_4H'] <= merged['Prev_1D'])]
                                            dc = merged[(merged['EMA200_4H'] < merged['EMA200_1D']) & (merged['Prev_4H'] >= merged['Prev_1D'])]
                                            
                                            if not gc.empty or not dc.empty:
                                                last_gc = gc.index[-1] if not gc.empty else pd.Timestamp.min.tz_localize('UTC')
                                                last_dc = dc.index[-1] if not dc.empty else pd.Timestamp.min.tz_localize('UTC')
                                                latest_idx = max(last_gc, last_dc)
                                                
                                                c_type = "🟢 골든크로스" if latest_idx == last_gc else "🔴 데드크로스"
                                                days_diff = (datetime.now(timezone.utc) - latest_idx).days
                                                if days_diff <= 90: c_type = f"🔥 {c_type}"
                                                    
                                                c_date = latest_idx.strftime('%Y-%m-%d %H:%M')
                                                c_price = f"${merged.loc[latest_idx, 'Close']:.2f}"
                                            else:
                                                c_type, c_date, c_price = "최근 1년 내 크로스 없음", "-", "-"
                                    
                                    mask = st.session_state.sp100_state_df['Symbol'] == sym
                                    st.session_state.sp100_state_df.loc[mask, '크로스 상태 (4H/1D EMA200)'] = c_type
                                    st.session_state.sp100_state_df.loc[mask, '크로스 날짜'] = c_date
                                    st.session_state.sp100_state_df.loc[mask, '크로스 당시 주가'] = c_price
                                    st.session_state.sp100_state_df.loc[mask, '업데이트 날짜'] = current_update_time

                                st.success(f"✅ {current_update_time} 기준, {labels[i]} 크로스 분석 완료!")
                                st.rerun() 
                                
                            except Exception as e:
                                st.error(f"야후 파이낸스 스캔 중 오류 발생: {str(e)}")

            display_cols = ['순위', '시총', 'Symbol', 'Name', 'Sector', '섹터 순위', '크로스 상태 (4H/1D EMA200)', '크로스 날짜', '크로스 당시 주가', '업데이트 날짜']
            st.dataframe(st.session_state.sp100_state_df[display_cols], use_container_width=True, hide_index=True, height=600)
