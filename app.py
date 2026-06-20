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

# 👇 분리된 모듈에서 필요한 기능들을 깔끔하게 가져옵니다. (코드 중복 제거)
from api_utils import (
    insert_db, update_db, delete_db, upload_image_to_supabase,
    load_trade_data, load_archive_data, get_recent_archive_context, load_sector_data, load_theory_db,
    get_gemini_keys, parse_ai_json, ask_gemini_dynamic, get_real_ocr_text, 
    get_real_ai_advice, render_ai_advice_block, render_blog_image_html, 
    render_crisp_image_html, get_file_group_info, execute_survival_trade
)
from market_research import fetch_financial_data, analyze_sector_with_ai, get_robust_session

# ==========================================
# --- 1. 데이터 포맷팅 및 UI 텍스트 사전 ---
# ==========================================
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

def format_krw_direct(krw_val):
    try:
        val = float(krw_val)
        if val <= 0: return "-"
        if val >= 1e12: 
            trillion = val / 1e12
            t_part = int(trillion)
            b_part = int((trillion - t_part) * 10000)
            if t_part == 0: return f"{b_part:,}억원"
            if b_part == 0: return f"{t_part:,}조원"
            return f"{t_part:,}조 {b_part:,}억원"
        elif val >= 1e8: 
            billion = val / 1e8
            return f"{int(billion):,}억원"
        return "-"
    except:
        return krw_val

INDUSTRY_GROUPING = {
    "Semiconductors": "반도체 및 장비", 
    "Computer Processing Hardware": "IT 하드웨어",
    "Computer Communications": "네트워크 통신 장비",
    "Electronic Equipment/Instruments": "IT 부품 및 전자기기",
    "Packaged Software": "소프트웨어 & 클라우드",
    "Internet Software/Services": "소프트웨어 & 클라우드",
    "Information Technology Services": "IT 서비스 & 컨설팅",
    "Internet Retail": "이커머스 & 온라인 유통",
    "Apparel/Footwear Retail": "의류 및 소비재 유통",
    "Specialty Stores": "전문 유통 채널",
    "Discount Stores": "대형 할인마트",
    "Pharmaceuticals: Major": "제약 & 바이오",
    "Biotechnology": "제약 & 바이오",
    "Medical Specialties": "의료 기기 & 장비",
    "Major Banks": "대형 은행",
    "Regional Banks": "지역 은행",
    "Investment Banks/Brokers": "투자은행 & 증권",
    "Finance/Rental/Leasing": "여신 전문 & 신용카드",
    "Property/Casualty Insurance": "손해보험",
    "Life/Health Insurance": "생명/건강보험",
    "Real Estate Investment Trusts": "리츠 (REITs)",
    "Broadcasting": "미디어 & 방송망",
    "Movies/Entertainment": "미디어 & 엔터테인먼트",
    "Auto Manufacturing": "자동차 & 모빌리티",
    "Motor Vehicles": "자동차 & 모빌리티",
    "Aerospace & Defense": "항공우주 & 국방",
    "Air Freight/Couriers": "항공 물류 & 택배",
    "Integrated Oil": "에너지 (석유/가스)",
    "Electric Utilities": "전력 & 에너지 유틸리티",
    "Beverages: Non-Alcoholic": "식음료 (음료 전문)",
    "Restaurants": "식음료 (F&B 프랜차이즈)",
    "Household/Personal Care": "가정용품 및 개인위생",
    "Industrial Machinery": "산업 기계 및 인프라",
    "Specialty Telecommunications": "통신 기기",
    "Computer Peripherals": "컴퓨터 주변기기",
    "Investment Managers": "투자 관리 및 펀드",
    "Other Metals/Minerals": "기타 금속 및 광물",
    "Managed Health Care": "의료 보험 및 헬스케어",
    "Trucks/Construction/Farm Machinery": "트럭 및 중장비"
}

NAME_TRANSLATIONS = {
    "AAPL": "Apple Inc. (애플)", "MSFT": "Microsoft (마이크로소프트)", "NVDA": "NVIDIA (엔비디아)",
    "GOOGL": "Alphabet Class A (구글)", "AMZN": "Amazon (아마존)", "META": "Meta Platforms (메타)", 
    "BRK-B": "Berkshire Hathaway (버크셔)", "LLY": "Eli Lilly (일라이 릴리)", "TSLA": "Tesla (테슬라)", 
    "AVGO": "Broadcom (브로드컴)", "V": "Visa (비자)", "JPM": "JPMorgan Chase (JP모건)", 
    "WMT": "Walmart (월마트)", "UNH": "UnitedHealth (유나이티드헬스)", "MA": "Mastercard (마스터카드)", 
    "PG": "Procter & Gamble (P&G)", "JNJ": "Johnson & Johnson (존슨앤드존슨)", "HD": "Home Depot (홈디포)", 
    "COST": "Costco (코스트코)", "MRK": "Merck & Co. (머크)", "ABBV": "AbbVie (애브비)", 
    "CRM": "Salesforce (세일즈포스)", "AMD": "Advanced Micro Devices (AMD)", "NFLX": "Netflix (넷플릭스)", 
    "KO": "Coca-Cola (코카콜라)", "PEP": "PepsiCo (펩시코)", "DIS": "Walt Disney (디즈니)", 
    "CSCO": "Cisco Systems (시스코)", "ADBE": "Adobe (어도비)", "QCOM": "Qualcomm (퀄컴)", 
    "INTC": "Intel (인텔)", "ARM": "ARM Holdings (암 홀딩스)", "PLTR": "Palantir (팔란티어)", 
    "RTX": "RTX Corporation (레이시온)", "PFE": "Pfizer (화이자)", "ORCL": "Oracle (오라클)", 
    "BAC": "Bank of America (뱅크오브아메리카)", "MS": "Morgan Stanley (모건스탠리)", 
    "GS": "Goldman Sachs (골드만삭스)", "WFC": "Wells Fargo (웰스파고)", "C": "Citigroup (씨티그룹)",
    "MU": "Micron Technology (마이크론)", "TSM": "Taiwan Semiconductor (TSMC)"
}

# ==========================================
# --- 2. 화면 구성 시작 (UI) ---
# ==========================================
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
                if position == "Long":
                    profit_calc = ((exit_price - entry_price) / entry_price) * margin * leverage
                else:
                    profit_calc = ((entry_price - exit_price) / entry_price) * margin * leverage
            
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
                
                insert_data = {
                    "date": date.strftime("%Y-%m-%d"), 
                    "ticker": ticker, 
                    "timeframe": timeframe, 
                    "setup_pattern": setup_pattern, 
                    "position": position, 
                    "result": result, 
                    "rr_ratio": rr_ratio, 
                    "profit": round(profit_calc, 2),
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
                        3. **가장 먼저**, 첨부된 차트 이미지 상단이나 텍스트를 보고 1) 어떤 종목(티커)인지 2) 몇 시간(분) 봉(타임프레임)인지 파악해서 분석의 첫 문장에 명확히 명시해 주세요.
                        4. **분석 결과 필수 포함**: analysis 항목에는 반드시 "아카이브에 기록된 원작자가 O시에 말한 OOO 근거에 따르면 현재는 OOO한 상태입니다"라는 식으로 언급 시점과 근거를 명시해서 현재 나의 관점을 검증해야 합니다.

                        반드시 아래의 JSON 형식으로만 답변을 출력해. 마크다운(` ```json ` 등)이나 다른 인사말은 절대 포함하지 마. 오직 중괄호 {{ }} 만 출력해.
                        
                        {{
                          "trend": "상승 / 하락 / 횡보 등 10자 이내 요약",
                          "key_level": "핵심 지지/저항 15자 이내 요약",
                          "momentum": "모멘텀 상태 15자 이내 요약",
                          "volume": "거래량 상태 10자 이내 요약",
                          "s_score": "0~4 사이의 정수 (유동성, 오더블록, 지지저항, 패턴 중첩 개수)",
                          "macro_news": "차트상 급등/급락이 관찰될 경우, 연관될 수 있는 매크로 이슈를 추론하여 1~2줄로 요약. 특이 흐름이 없으면 '특이 동향 없음' 기재.",
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
                st.success("API 및 자금 세팅이 활성화되었습니다! 이제 생존 매매 탭을 이용할 수 있습니다.")

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
                    with st.spinner("비트겟 서버로 주문 전송 중..."):
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
# --- Tab 5: 분석 아카이브 ---
# ==============================
with tab5:
    st.header("📁 분석 자료 아카이브 (AI 자동화)")
    df_archive = load_archive_data()
    sub_tab_a, sub_tab_b = st.tabs(["👨‍🏫 타인 분석 스크랩", "👀 나의 관점 (Watchlist)"])
    
    with sub_tab_a:
        with st.expander("➕ 새로운 스크랩 추가하기", expanded=False):
            col_header, col_reset = st.columns([8, 2])
            with col_header:
                st.markdown("### 📝 새 분석 스크랩 작성")
            with col_reset:
                if st.button("🗑️ 첨부 일괄 삭제", use_container_width=True, help="업로드된 사진을 모두 지웁니다."):
                    st.session_state.uploader_key += 1
                    st.rerun()

            st.markdown("---")
            col_up1, col_up2 = st.columns(2)
            with col_up1:
                st.markdown("#### 🖼️ 1. 포스팅 원본 (글 캡처)")
                arch_imgs_blog = st.file_uploader("인사이트 내용 캡처 (AI가 자동으로 텍스트 추출)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key=f"arch_imgs_blog_{st.session_state.uploader_key}", label_visibility="collapsed")
            with col_up2:
                st.markdown("#### 🔍 2. 세부 고해상도 차트")
                arch_imgs_detail = st.file_uploader("고해상도 차트 (AI가 차트를 분석합니다)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, key=f"arch_imgs_detail_{st.session_state.uploader_key}", label_visibility="collapsed")
            
            with st.form("archive_form_others", clear_on_submit=True):
                col1, col2, col3 = st.columns(3)
                with col1: arch_date1 = st.date_input("스크랩 날짜", datetime.today())
                with col2: arch_ticker1 = st.text_input("관련 종목명 (예: BTC, NDX)").upper()
                with col3: arch_source1 = st.text_input("출처/제목 (예: 쉽알남 시황)")
                
                ticker_mapping_input = {}
                selected_charts_for_ai = []
                
                if arch_imgs_detail:
                    st.divider()
                    st.markdown("### 🤖 세부 차트별 AI 분석 설정")
                    st.caption("여러 장의 차트를 올리셨군요! 각 차트가 어떤 종목인지 알려주면 AI가 훨씬 정확하게 분석합니다.")
                    
                    batch_ticker = st.text_input("💡 [일괄 적용] 모든 차트에 적용할 기본 종목명 (비워두면 위의 '관련 종목명' 사용)", placeholder="예: BTCUSDT")
                    
                    st.markdown("**📌 개별 차트 종목 지정 (위 일괄 적용과 다를 경우에만 개별 수정하세요)**")
                    cols = st.columns(3)
                    for idx, img in enumerate(arch_imgs_detail):
                        selected_charts_for_ai.append(img.name)
                        with cols[idx % 3]:
                            ticker_mapping_input[img.name] = st.text_input(f"차트 {idx+1} ({img.name[:8]}...)", key=f"t_{st.session_state.uploader_key}_{idx}")
                
                if st.form_submit_button("☁️ 스크랩 & 무료 AI 분석 시작", use_container_width=True, type="primary"):
                    if not arch_ticker1: st.error("관련 종목명을 최소 1개 이상 입력해주세요!")
                    else:
                        with st.spinner("무료 AI(Gemini)가 분석 중입니다... 여러 장을 올리면 시간이 조금 걸립니다! 🤖"):
                            blog_urls, detail_urls = [], []
                            ai_advice_final_mapping, ocr_final_mapping = {}, {}
                            date_str = arch_date1.strftime("%Y-%m-%d")
                            
                            if arch_imgs_blog:
                                arch_imgs_blog = sorted(arch_imgs_blog, key=lambda x: int(get_file_group_info(x.name)[0]) if str(get_file_group_info(x.name)[0]).isdigit() else 9999)
                                for img_file in arch_imgs_blog:
                                    group, sub = get_file_group_info(img_file.name)
                                    url = upload_image_to_supabase(img_file, f"arch_blog_{group}_{sub}")
                                    if url:
                                        blog_urls.append(url)
                                        ocr_final_mapping[group] = get_real_ocr_text(url)
                                        time.sleep(1.5) 
                            
                            if arch_imgs_detail:
                                for img_file in arch_imgs_detail:
                                    group, sub = get_file_group_info(img_file.name)
                                    url = upload_image_to_supabase(img_file, f"arch_detail_{group}_{sub}")
                                    if url:
                                        detail_urls.append(url)
                                        if img_file.name in selected_charts_for_ai:
                                            specific_ticker = ticker_mapping_input.get(img_file.name, "").strip()
                                            if not specific_ticker: specific_ticker = batch_ticker.strip()
                                            if not specific_ticker: specific_ticker = arch_ticker1.strip()
                                            
                                            associated_text = ocr_final_mapping.get(group, "")
                                            ai_advice_final_mapping[f"{group}_{sub}"] = get_real_ai_advice(url, specific_ticker, associated_text)
                                            time.sleep(1.5) 

                            insert_data = {
                                "date": date_str, "ticker": arch_ticker1, "category": "타인분석", "source_view": arch_source1,
                                "chart_image_paths": "|".join(blog_urls), "detail_image_paths": "|".join(detail_urls), "memo": "",
                                "ai_advice_mapping": json.dumps(ai_advice_final_mapping, ensure_ascii=False),
                                "ocr_text_mapping": json.dumps(ocr_final_mapping, ensure_ascii=False)
                            }
                            insert_db("analysis_archive", insert_data)
                            st.session_state.uploader_key += 1
                        st.success("무료 AI 분석 및 클라우드 저장 완료!")
                        st.rerun()

        df_others = df_archive[df_archive['category'] == '타인분석'].copy()
        if not df_others.empty:
            df_others = df_others.sort_values(by='date', ascending=False).reset_index(drop=True)
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
                    st.markdown(f"**출처/제목:** {arch_data['source_view']}")
                with col_del:
                    if st.button("🗑️ 삭제하기", type="primary", use_container_width=True):
                        delete_db("analysis_archive", "id", arch_id_current)
                        st.rerun()
                
                with st.expander("⚙️ 스크랩 정보 수정", expanded=False):
                    with st.form(key=f"edit_basic_info_form_{arch_id_current}"):
                        c1, c2, c3 = st.columns(3)
                        with c1: new_date = st.date_input("날짜", value=pd.to_datetime(arch_data['date']).date())
                        with c2: new_ticker = st.text_input("종목명", value=arch_data['ticker'])
                        with c3: new_source = st.text_input("출처/제목", value=arch_data['source_view'])
                        if st.form_submit_button("정보 업데이트", use_container_width=True):
                            update_db("analysis_archive", "id", arch_id_current, {"date": new_date.strftime("%Y-%m-%d"), "ticker": new_ticker.upper(), "source_view": new_source})
                            st.rerun()
                st.write("")
                
                with st.form(key=f"edit_arch_memo_form_{arch_id_current}"):
                    st.markdown("### 📝 전체 핵심 요약 (나의 인사이트)")
                    edit_memo = st.text_area("배울 점 입력", value=arch_data.get("memo", ""), height=100)
                    if st.form_submit_button("클라우드 저장", use_container_width=True):
                        update_db("analysis_archive", "id", arch_id_current, {"memo": edit_memo})
                        st.rerun()

                st.divider()
                
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
                shown_legacy_advice = set()

                if valid_blogs:
                    for idx, path in enumerate(valid_blogs):
                        current_blog_idx = idx + 1
                        filename = path.split('/')[-1]
                        group = filename.split('_blog_')[1].split('_')[0] if '_blog_' in filename else str(idx)
                        
                        matched_detail_paths = detail_dict.get(group, [])
                        badge_html = f"""<div style='margin-bottom: 8px;'><span style="background-color:#f0f2f6; padding:6px 12px; border-radius:6px; color:#333; font-weight:bold; font-size:15px; border: 1px solid #ddd;">📷 [ {current_blog_idx} / {total_blogs} ] 원본 데이터</span></div>"""
                        
                        if matched_detail_paths:
                            rendered_details.update(matched_detail_paths)
                            state_key = f"show_blog_{arch_id_current}_{group}"
                            if state_key not in st.session_state: st.session_state[state_key] = False
                            show_blog = st.session_state[state_key]
                            num = group
                            
                            if show_blog:
                                st.markdown("---")
                                col_blog_view, _ = st.columns([4, 6])
                                with col_blog_view:
                                    st.markdown(badge_html, unsafe_allow_html=True)
                                    st.markdown(render_blog_image_html(path), unsafe_allow_html=True)
                                    if st.button("❌ 원본 숨기기", key=f"close_btn_{state_key}", use_container_width=True):
                                        st.session_state[state_key] = False
                                        st.rerun()
                                
                                st.markdown("#### 🔍 세부 차트 분석")
                                for idx_mdp, mdp in enumerate(matched_detail_paths):
                                    c_chart, c_ai = st.columns([6.5, 3.5], gap="medium")
                                    with c_chart:
                                        st.markdown(render_crisp_image_html(mdp), unsafe_allow_html=True)
                                    with c_ai:
                                        fname = mdp.split('/')[-1]
                                        if '_detail_' in fname:
                                            parts = fname.split('_detail_')[1].split('_')
                                            g = parts[0]
                                            s = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                                            k = f"{g}_{s}"
                                            
                                            if k in ai_advice_mapping and ai_advice_mapping[k]:
                                                render_ai_advice_block(f"🤖 차트 {g}-{s} AI 분석", ai_advice_mapping[k])
                                            elif g in ai_advice_mapping and ai_advice_mapping[g] and g not in shown_legacy_advice:
                                                render_ai_advice_block(f"🤖 차트 AI 분석", ai_advice_mapping[g])
                                                shown_legacy_advice.add(g)

                                        display_txt = ocr_mapping.get(num, "").strip()
                                        st.markdown("#### 📄 본문 텍스트 (OCR)")
                                        if display_txt: st.info(display_txt)
                                        else: st.info("*(추출된 텍스트가 없습니다.)*")
                                        
                                        with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                            with st.form(key=f"edit_ocr_open_{arch_id_current}_{num}_{idx_mdp}"):
                                                edited_ocr = st.text_area("내용 교정", value=display_txt, height=150)
                                                if st.form_submit_button("저장", use_container_width=True):
                                                    ocr_mapping[num] = edited_ocr
                                                    update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                                    st.rerun()

                            else:
                                st.markdown("---")
                                col_btn, _ = st.columns([3, 7])
                                with col_btn:
                                    if st.button(f"🔍 [ {current_blog_idx} / {total_blogs} ] 원본 이미지 보기", key=f"open_btn_{state_key}", use_container_width=True):
                                        st.session_state[state_key] = True
                                        st.rerun()
                                
                                for idx_mdp, mdp in enumerate(matched_detail_paths):
                                    c_chart, c_ai = st.columns([6.5, 3.5], gap="medium")
                                    with c_chart:
                                        st.markdown(render_crisp_image_html(mdp), unsafe_allow_html=True)
                                    with c_ai:
                                        fname = mdp.split('/')[-1]
                                        if '_detail_' in fname:
                                            parts = fname.split('_detail_')[1].split('_')
                                            g = parts[0]
                                            s = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                                            k = f"{g}_{s}"
                                            
                                            if k in ai_advice_mapping and ai_advice_mapping[k]:
                                                render_ai_advice_block(f"🤖 차트 {g}-{s} AI 분석", ai_advice_mapping[k])
                                            elif g in ai_advice_mapping and ai_advice_mapping[g] and g not in shown_legacy_advice:
                                                render_ai_advice_block(f"🤖 차트 AI 분석", ai_advice_mapping[g])
                                                shown_legacy_advice.add(g)

                                        display_txt = ocr_mapping.get(num, "").strip()
                                        st.markdown("#### 📄 본문 텍스트 (OCR)")
                                        if display_txt: st.info(display_txt)
                                        else: st.info("*(추출된 텍스트가 없습니다.)*")
                                        
                                        with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                            with st.form(key=f"edit_ocr_closed_{arch_id_current}_{num}_{idx_mdp}"):
                                                edited_ocr = st.text_area("내용 교정", value=display_txt, height=150)
                                                if st.form_submit_button("저장", use_container_width=True):
                                                    ocr_mapping[num] = edited_ocr
                                                    update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                                    st.rerun()
                        else:
                            st.markdown("---")
                            c_blog, c_ocr = st.columns([6.5, 3.5], gap="medium")
                            num = group
                            with c_blog:
                                st.markdown(badge_html, unsafe_allow_html=True)
                                st.markdown(render_blog_image_html(path), unsafe_allow_html=True)
                            with c_ocr:
                                if num in ai_advice_mapping and ai_advice_mapping[num]: 
                                    render_ai_advice_block("🤖 AI 분석", ai_advice_mapping[num])
                                
                                raw_txt = ocr_mapping.get(num, "")
                                display_txt = str(raw_txt).strip() if pd.notna(raw_txt) else ""
                                st.markdown("#### 📄 본문 텍스트 (OCR)")
                                if display_txt: st.info(display_txt)
                                else: st.info("*(추출된 텍스트가 없습니다.)*")
                                
                                with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                    with st.form(key=f"edit_ocr_alone_{arch_id_current}_{num}"):
                                        edited_ocr = st.text_area("내용 교정", value=display_txt, height=150)
                                        if st.form_submit_button("저장", use_container_width=True):
                                            ocr_mapping[num] = edited_ocr
                                            update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                            st.rerun()
                else: st.info("저장된 포스팅 원본 이미지가 없습니다.")
                
                unrendered_details = [dp for dp in valid_details if dp not in rendered_details]
                if unrendered_details:
                    st.markdown("### 📎 기타 세부 차트")
                    for idx_unrendered, path in enumerate(unrendered_details):
                        c_u_img, c_u_txt = st.columns([6.5, 3.5], gap="medium")
                        with c_u_img: st.markdown(render_crisp_image_html(path), unsafe_allow_html=True)
                        with c_u_txt:
                            fname = path.split('/')[-1]
                            if '_detail_' in fname:
                                parts = fname.split('_detail_')[1].split('_')
                                g = parts[0]
                                s = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                                k = f"{g}_{s}"
                                
                                if k in ai_advice_mapping and ai_advice_mapping[k]:
                                    render_ai_advice_block(f"🤖 차트 {g}-{s} 조언", ai_advice_mapping[k])
                                elif g in ai_advice_mapping and ai_advice_mapping[g] and g not in shown_legacy_advice:
                                    render_ai_advice_block("🤖 차트 AI 분석", ai_advice_mapping[g])
                                    shown_legacy_advice.add(g)

                            raw_txt = ocr_mapping.get(num, "")
                            display_txt = str(raw_txt).strip() if pd.notna(raw_txt) else ""
                            st.markdown("#### 📄 본문 텍스트 (OCR)")
                            if display_txt: st.info(display_txt)
                            else: st.info("*(추출된 텍스트가 없습니다.)*")
                            
                            with st.expander("✏️ 텍스트 입력/교정", expanded=False):
                                with st.form(key=f"edit_ocr_other_{arch_id_current}_{num}_{idx_unrendered}"):
                                    edited_ocr = st.text_area("내용 교정", value=display_txt, height=150)
                                    if st.form_submit_button("저장", use_container_width=True):
                                        ocr_mapping[num] = edited_ocr
                                        update_db("analysis_archive", "id", arch_id_current, {"ocr_text_mapping": json.dumps(ocr_mapping, ensure_ascii=False)})
                                        st.rerun()

    with sub_tab_b:
        st.markdown("### 👀 나의 관점 (Watchlist)")
        st.caption("Tab 2(AI 차트 & 관점 분석)에서 분석하고 저장한 S급 셋업 후보들이 이곳에 모입니다.")
        
        df_myview = df_archive[df_archive['category'] == '나의관점'].copy()
        
        if not df_myview.empty:
            df_myview = df_myview.sort_values(by='date', ascending=False).reset_index(drop=True)
            selected_myview = st.dataframe(df_myview[["date", "ticker", "source_view"]], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
            
            selected_rows_myview = selected_myview.get('selection', {}).get('rows', [])
            if selected_rows_myview:
                st.divider()
                my_data = df_myview.iloc[selected_rows_myview[0]]
                my_id = my_data['id']
                
                col_title, col_del = st.columns([8.5, 1.5])
                with col_title:
                    st.markdown(f"## 🎯 {my_data['date']} | {my_data['ticker']} 관점")
                with col_del:
                    if st.button("🗑️ 삭제하기", type="primary", use_container_width=True, key=f"del_my_{my_id}"):
                        delete_db("analysis_archive", "id", my_id)
                        st.rerun()
                
                col_img, col_txt = st.columns([6.5, 3.5], gap="large")
                with col_img:
                    if my_data.get('chart_image_paths'):
                        urls = my_data['chart_image_paths'].split('|')
                        for u in urls:
                            if u: st.markdown(render_crisp_image_html(u), unsafe_allow_html=True)
                with col_txt:
                    st.info(f"**💡 나의 셋업 관점:**\n\n{my_data['source_view']}")
                    render_ai_advice_block("🤖 AI 멘토의 검증 피드백", my_data['memo'])
        else:
            st.info("아직 저장된 관점이 없습니다. '🔎 AI 차트 & 관점 분석' 탭에서 분석 후 S급 셋업을 저장해 보세요!")

# ==============================
# --- Tab 6: 섹터 & 주도주 맵 ---
# ==============================
with tab6:
    st.header("🏢 섹터 & 주도주 맵 (AI 리서 저장소)")
    st.info("야후 파이낸스와 나스닥(Nasdaq)을 결합하여 완벽한 실적 데이터와 4H/1D 이평선 크로스, 최신 뉴스를 가져옵니다.")
    
    sub_tab_research, sub_tab_top100, sub_tab_kr_top100 = st.tabs(["🏢 내 종목 리서치", "🇺🇸 미국 시총 Top 100 맵", "🇰🇷 한국 코스피 Top 100 맵"])
    
    with sub_tab_research:
        with st.expander("➕ 새 종목 리서치 자동화 추가하기"):
            with st.form("new_sector_stock"):
                c1, c2 = st.columns(2)
                s_ticker = c1.text_input("야후 파이낸스 티커 (한국종목은 005930 또는 005930.KS 형태 입력)")
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
                
                st.markdown(f"#### 📈 {stock_data['ticker']} 실시간 차트 (TradingView)")
                tv_widget = f"""
                <div class="tradingview-widget-container" style="height:650px;width:100%; margin-bottom: 20px;">
                  <div id="tradingview_{stock_data['ticker']}" style="height:calc(100% - 32px);width:100%"></div>
                  <script type="text/javascript" src="[https://s3.tradingview.com/tv.js](https://s3.tradingview.com/tv.js)"></script>
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

    with sub_tab_top100:
        st.markdown("### 🇺🇸 미국 시총 상위 Top 100 기업 (실시간 데이터 기준)")
        st.info("💡 **알림:** 실시간 트레이딩뷰(TradingView) 서버에서 진성 미국 시가총액 100위 명단을 즉시 스캔하여 줄을 세웁니다.")

        if st.button("🔄 실시간 순수 미국 시총 Top 100 스캔 시작", type="primary", key="us_btn"):
            with st.spinner("미국 시장 전 종목을 스캔하여 실시간 시총 100위를 선별 중입니다... (약 2초 소요)"):
                try:
                    url = "[https://scanner.tradingview.com/america/scan](https://scanner.tradingview.com/america/scan)"
                    payload = {
                        "filter": [
                            {"left": "market_cap_basic", "operation": "nempty"},
                            {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
                            {"left": "exchange", "operation": "in_range", "right": ["AMEX", "NASDAQ", "NYSE"]} 
                        ],
                        "options": {"lang": "en"},
                        "markets": ["america"],
                        "symbols": {"query": {"types": []}, "tickers": []},
                        "columns": ["name", "description", "sector", "industry", "market_cap_basic"],
                        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                        "range": [0, 250] 
                    }
                    headers = {"User-Agent": "Mozilla/5.0"}
                    res = requests.post(url, json=payload, headers=headers)
                    data = res.json()
                    
                    df_list = []
                    seen_tickers = set()
                    target_exact = ['JPM', 'ORCL', 'BAC', 'MS', 'GS', 'WFC', 'C']
                    
                    for item in data.get('data', []):
                        if len(df_list) >= 100: break
                        sym = item['d'][0] 
                        name_raw = item['d'][1]
                        ind_raw = item['d'][3]
                        mcap = item['d'][4]
                        base_ticker = re.split(r'[-/.]', sym)[0]
                        if base_ticker == 'BML': continue
                        if base_ticker in target_exact:
                            if sym != base_ticker: continue 
                        if base_ticker in ['GOOG', 'GOOGL', 'GOOGM', 'GOOGN']: 
                            base_ticker = 'GOOG'
                            if sym not in ['GOOG', 'GOOGL']: continue
                        if base_ticker in ['BRK.A', 'BRK.B', 'BRK']: base_ticker = 'BRK' 
                        if base_ticker in ['FOXA', 'FOX']: base_ticker = 'FOX'
                        if base_ticker in ['NWSA', 'NWS']: base_ticker = 'NWS'
                        if base_ticker in ['UAA', 'UA']: base_ticker = 'UA'
                        if base_ticker in seen_tickers: continue
                        seen_tickers.add(base_ticker)
                        
                        sym_clean = sym.replace('.', '-').replace('/', '-')
                        ind_trans = INDUSTRY_GROUPING.get(ind_raw, ind_raw) 
                        name_trans = NAME_TRANSLATIONS.get(sym_clean, name_raw) 
                        
                        df_list.append({
                            '순위': len(df_list) + 1,
                            '시총': format_mcap_krw(mcap),
                            'Symbol': sym_clean,
                            'Name': name_trans,
                            '산업군(Industry)': ind_trans,
                            '시가총액_num': mcap,
                            '분야 순위': "-",
                            '크로스 상태 (4H/1D EMA200)': "대기 중",
                            '크로스 날짜': "-",
                            '크로스 당시 주가': "-",
                            '업데이트 날짜': "-"
                        })
                    
                    new_df = pd.DataFrame(df_list)
                    new_df['분야 내 순위'] = new_df.groupby('산업군(Industry)')['시가총액_num'].rank(ascending=False, method='min')
                    new_df['분야 순위'] = new_df['분야 내 순위'].apply(lambda x: f"산업 {int(x)}위" if pd.notna(x) else "-")
                    new_df = new_df.drop(columns=['분야 내 순위'])
                    
                    st.session_state.sp100_state_df = new_df
                    st.success("✅ 실시간 미국 시총 Top 100 리스트 업데이트 완료!")
                except Exception as e:
                    st.error(f"데이터 스캔 중 오류가 발생했습니다: {e}")

        if not st.session_state.sp100_state_df.empty:
            st.markdown("#### 🗺️ S&P 500 주도주 히트맵 (실시간 자금 흐름)")
            st.caption("💡 블록의 크기는 시가총액(Market Cap)을, 색상은 오늘 하루의 등락률을 나타냅니다. 마우스를 올리면 상세 정보를 볼 수 있습니다.")
            heatmap_widget = """
            <div class="tradingview-widget-container" style="height: 700px; width: 100%;">
              <div class="tradingview-widget-container__widget" style="height: 100%; width: 100%;"></div>
              <script type="text/javascript" src="[https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js](https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js)" async>
              {
              "exchanges": ["NYSE", "NASDAQ", "AMEX"],
              "dataSource": "SPX500",
              "grouping": "sector",
              "blockSize": "market_cap_basic",
              "blockColor": "change",
              "locale": "kr",
              "symbolUrl": "",
              "colorTheme": "light",
              "hasTopBar": false,
              "isDataSetEnabled": false,
              "isZoomEnabled": true,
              "hasSymbolTooltip": true,
              "width": "100%",
              "height": 700
            }
              </script>
            </div>
            """
            components.html(heatmap_widget, height=700)
            st.markdown("---")
            
            st.markdown("#### 📈 나스닥 100 기간별 수익률 지표")
            try:
                session = get_robust_session()[0]
                sp500_df = pd.DataFrame()
                for tkr in ["^NDX", "QQQ"]:
                    for _ in range(2):
                        try:
                            temp_df = yf.download(tkr, period="4y", interval="1d", progress=False, session=session)
                            if not temp_df.empty:
                                sp500_df = temp_df
                                break
                        except: time.sleep(1)
                    if not sp500_df.empty: break

                if not sp500_df.empty:
                    if isinstance(sp500_df.columns, pd.MultiIndex): close_series = sp500_df['Close'].iloc[:, 0]
                    else: close_series = sp500_df['Close']
                    curr = close_series.iloc[-1]
                    def ret(days):
                        if len(close_series) > days: return float((curr - close_series.iloc[-(days+1)]) / close_series.iloc[-(days+1)] * 100)
                        return 0.0
                    ndx_data = {"1일": ret(1), "7일": ret(5), "1개월": ret(21), "3개월": ret(63), "6개월": ret(126), "1년": ret(252), "3년": ret(756)}
                    ndx_df = pd.DataFrame([ndx_data])
                    def color_val(val):
                        color = '#ef4444' if val < 0 else '#22c55e'
                        return f"color: {color}; font-weight: bold;"
                    formatted_df = ndx_df.map(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)
                    st.dataframe(formatted_df.style.map(lambda x: color_val(float(str(x).replace('%', '')))), use_container_width=True, hide_index=True)
                else: st.warning("야후 파이낸스 통신망 일시 지연. 새로고침을 눌러주세요.")
            except Exception as e: st.error(f"데이터를 불러오는 중 오류 발생: {e}")
                
            st.markdown("#### 📊 나스닥 100 (US TECH 100 CASH) 최근 1년 흐름 (주봉 실시간 차트)")
            ndx_tv_widget = """
            <div class="tradingview-widget-container" style="height:350px;width:100%;">
              <div id="tradingview_ndx" style="height:calc(100% - 32px);width:100%"></div>
              <script type="text/javascript" src="[https://s3.tradingview.com/tv.js](https://s3.tradingview.com/tv.js)"></script>
              <script type="text/javascript">
              new TradingView.widget({
              "autosize": true, "symbol": "OANDA:NAS100USD", "interval": "W", "timezone": "Etc/UTC",
              "theme": "light", "style": "1", "locale": "kr", "enable_publishing": false,
              "hide_top_toolbar": true, "hide_legend": true, "save_image": false,
              "container_id": "tradingview_ndx"
              });
              </script>
            </div>
            """
            components.html(ndx_tv_widget, height=350)
            st.markdown("---")

            symbols = st.session_state.sp100_state_df['Symbol'].tolist()
            chunks = [symbols[i:i+25] for i in range(0, 100, 25)]
            labels = ["1위~25위", "26위~50위", "51위~75위", "76위~100위"]
            st.caption("야후 파이낸스 데이터 차단(Rate Limit)을 방지하기 위해 25개 종목씩 나누어 '4시간봉 EMA 200 vs 1일봉 EMA 200' 크로스 현황을 정밀 스캔합니다.")
            cols = st.columns(4)
            for i in range(4):
                if i < len(chunks):
                    if cols[i].button(f"🚀 {labels[i]} 스캔", use_container_width=True, key=f"btn_us_scan_{i}"):
                        with st.spinner(f"{labels[i]} 실시간 데이터 스캔 중..."):
                            time.sleep(2)
                            try:
                                session = get_robust_session()[0]
                                data_1d_raw = yf.download(chunks[i], period="2y", interval="1d", progress=False, session=session)
                                data_1h_raw = yf.download(chunks[i], period="730d", interval="1h", progress=False, session=session)
                                
                                if 'Close' in data_1d_raw: data_1d = data_1d_raw['Close']
                                else: data_1d = data_1d_raw
                                if 'Close' in data_1h_raw: data_1h = data_1h_raw['Close']
                                else: data_1h = data_1h_raw
                                if isinstance(data_1d, pd.Series): data_1d = data_1d.to_frame(name=chunks[i][0])
                                if isinstance(data_1h, pd.Series): data_1h = data_1h.to_frame(name=chunks[i][0])
                                current_update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                
                                for sym in chunks[i]:
                                    if sym not in data_1d.columns or sym not in data_1h.columns: c_type, c_date, c_price = "데이터 부족", "-", "-"
                                    else:
                                        df_sym_1d = data_1d[sym].dropna()
                                        df_sym_1h = data_1h[sym].dropna()
                                        if len(df_sym_1d) < 150 or len(df_sym_1h) < 150: c_type, c_date, c_price = "상장기간 부족", "-", "-"
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
                                st.error(f"야후 파이낸스 스캔 중 오류 발생 (잠시 후 다시 시도해주세요): {str(e)}")

            display_cols = ['순위', '시총', 'Symbol', 'Name', '산업군(Industry)', '분야 순위', '크로스 상태 (4H/1D EMA200)', '크로스 날짜', '크로스 당시 주가', '업데이트 날짜']
            st.dataframe(st.session_state.sp100_state_df[display_cols], use_container_width=True, hide_index=True, height=1100)

    with sub_tab_kr_top100:
        st.markdown("### 🇰🇷 한국 코스피 상위 Top 100 기업 (실시간 데이터 기준)")
        st.info("💡 **알림:** 실시간 트레이딩뷰(TradingView) 서버에서 대한민국 코스피(KOSPI) 시가총액 최상위 100개 명단(우선주 완전 필터링)을 즉시 스캔하여 묶어냅니다.")

        if st.button("🔄 실시간 한국 코스피 Top 100 스캔 시작", type="primary", key="btn_kr_scan"):
            with st.spinner("코스피 전 종목을 스캔하여 실시간 시총 100위를 선별 중입니다... (약 2초 소요)"):
                try:
                    url = "[https://scanner.tradingview.com/korea/scan](https://scanner.tradingview.com/korea/scan)"
                    payload = {
                        "filter": [
                            {"left": "market_cap_basic", "operation": "nempty"},
                            {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
                            {"left": "exchange", "operation": "in_range", "right": ["KRX"]} 
                        ],
                        "options": {"lang": "ko"},
                        "markets": ["korea"],
                        "symbols": {"query": {"types": []}, "tickers": []},
                        "columns": ["name", "description", "sector", "industry", "market_cap_basic"],
                        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                        "range": [0, 200] 
                    }
                    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
                    res = requests.post(url, json=payload, headers=headers)
                    
                    if res.status_code != 200: raise Exception(f"트레이딩뷰 서버 응답 지연 (상태 코드: {res.status_code})")
                    data = res.json()
                    
                    df_list = []
                    seen_tickers = set()
                    
                    for item in data.get('data', []):
                        if len(df_list) >= 100: break
                        sym = item['d'][0] 
                        name_raw = item['d'][1]
                        ind_raw = item['d'][3]
                        mcap = item['d'][4]
                        
                        base_ticker = sym.split(':')[-1]
                        
                        if len(base_ticker) == 6 and not base_ticker.endswith('0'): continue
                        if "우" in name_raw and ("우B" in name_raw or "우(" in name_raw or name_raw.endswith("우")): continue
                        
                        if base_ticker in seen_tickers: continue
                        seen_tickers.add(base_ticker)
                        yf_ticker = f"{base_ticker}.KS"
                        
                        df_list.append({
                            '순위': len(df_list) + 1,
                            '시총': format_krw_direct(mcap),
                            'Symbol': base_ticker,
                            'YF_Symbol': yf_ticker,
                            'Name': name_raw,
                            '산업군(Industry)': ind_raw if ind_raw else "기타",
                            '시가총액_num': mcap,
                            '분야 순위': "-",
                            '크로스 상태 (4H/1D EMA200)': "대기 중",
                            '크로스 날짜': "-",
                            '크로스 당시 주가': "-",
                            '업데이트 날짜': "-"
                        })
                    
                    new_df = pd.DataFrame(df_list)
                    new_df['분야 내 순위'] = new_df.groupby('산업군(Industry)')['시가총액_num'].rank(ascending=False, method='min')
                    new_df['분야 순위'] = new_df['분야 내 순위'].apply(lambda x: f"산업 {int(x)}위" if pd.notna(x) else "-")
                    new_df = new_df.drop(columns=['분야 내 순위'])
                    
                    st.session_state.kospi100_state_df = new_df
                    st.success("✅ 불순물 및 우선주 제거, 순수 코스피 보통주 Top 100 리스트 업데이트 완료!")
                except Exception as e:
                    st.error(f"데이터 스캔 중 오류가 발생했습니다: {e}")

        if not st.session_state.kospi100_state_df.empty:
            st.markdown("#### 🗺️ 한국 코스피 주도주 히트맵 (실시간 자금 흐름)")
            st.caption("💡 블록의 크기는 시가총액(Market Cap)을, 색상은 오늘 하루의 등락률을 나타냅니다. 마우스를 올리면 상세 정보를 볼 수 있습니다.")
            heatmap_widget_kr = """
            <div class="tradingview-widget-container" style="height: 700px; width: 100%;">
              <div class="tradingview-widget-container__widget" style="height: 100%; width: 100%;"></div>
              <script type="text/javascript" src="[https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js](https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js)" async>
              {
              "exchanges": ["KRX"],
              "dataSource": "KOSPI200",
              "market": "south_korea",
              "grouping": "sector",
              "blockSize": "market_cap_basic",
              "blockColor": "change",
              "locale": "kr",
              "symbolUrl": "",
              "colorTheme": "light",
              "hasTopBar": false,
              "isDataSetEnabled": false,
              "isZoomEnabled": true,
              "hasSymbolTooltip": true,
              "width": "100%",
              "height": 700
            }
              </script>
            </div>
            """
            components.html(heatmap_widget_kr, height=700)
            st.markdown("---")
            
            st.markdown("#### 📈 코스피(KOSPI) 기간별 수익률 지표")
            try:
                session = get_robust_session()[0]
                kospi_df = pd.DataFrame()
                for _ in range(2):
                    try:
                        temp_df = yf.download("^KS11", period="4y", interval="1d", progress=False, session=session)
                        if not temp_df.empty:
                            kospi_df = temp_df
                            break
                    except: time.sleep(1)

                if not kospi_df.empty:
                    if isinstance(kospi_df.columns, pd.MultiIndex): close_series = kospi_df['Close'].iloc[:, 0]
                    else: close_series = kospi_df['Close']
                    curr = close_series.iloc[-1]
                    def ret(days):
                        if len(close_series) > days: return float((curr - close_series.iloc[-(days+1)]) / close_series.iloc[-(days+1)] * 100)
                        return 0.0
                    kr_data = {"1일": ret(1), "7일": ret(5), "1개월": ret(21), "3개월": ret(63), "6개월": ret(126), "1년": ret(252), "3년": ret(756)}
                    kr_df = pd.DataFrame([kr_data])
                    def color_val(val):
                        color = '#ef4444' if val < 0 else '#22c55e'
                        return f"color: {color}; font-weight: bold;"
                    formatted_kr_df = kr_df.map(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)
                    st.dataframe(formatted_kr_df.style.map(lambda x: color_val(float(str(x).replace('%', '')))), use_container_width=True, hide_index=True)
                else: st.warning("야후 파이낸스 통신망 일시 지연. 새로고침을 눌러주세요.")
            except Exception as e: st.error(f"데이터를 불러오는 중 오류 발생: {e}")
                
            st.markdown("#### 📊 코스피 (KOSPI) 최근 1년 흐름 (주봉 실시간 차트)")
            kr_tv_widget = """
            <div class="tradingview-widget-container" style="height:350px;width:100%;">
              <div id="tradingview_kospi" style="height:calc(100% - 32px);width:100%"></div>
              <script type="text/javascript" src="[https://s3.tradingview.com/tv.js](https://s3.tradingview.com/tv.js)"></script>
              <script type="text/javascript">
              new TradingView.widget({
              "autosize": true, "symbol": "TVC:KOSPI", "interval": "W", "timezone": "Asia/Seoul",
              "theme": "light", "style": "1", "locale": "kr", "enable_publishing": false,
              "hide_top_toolbar": true, "hide_legend": true, "save_image": false,
              "container_id": "tradingview_kospi"
              });
              </script>
            </div>
            """
            components.html(kr_tv_widget, height=350)
            st.markdown("---")

            yf_symbols = st.session_state.kospi100_state_df['YF_Symbol'].tolist()
            ui_symbols = st.session_state.kospi100_state_df['Symbol'].tolist()
            chunks_yf = [yf_symbols[i:i+25] for i in range(0, 100, 25)]
            chunks_ui = [ui_symbols[i:i+25] for i in range(0, 100, 25)]
            labels_kr = ["1위~25위", "26위~50위", "51위~75위", "76위~100위"]
            
            st.caption("야후 파이낸스 데이터 차단(Rate Limit)을 방지하기 위해 25개 종목씩 나누어 '4시간봉 EMA 200 vs 1일봉 EMA 200' 크로스 현황을 정밀 스캔합니다.")
            cols_kr = st.columns(4)
            for i in range(4):
                if i < len(chunks_yf):
                    if cols_kr[i].button(f"🚀 코스피 {labels_kr[i]} 스캔", use_container_width=True, key=f"btn_kr_{i}"):
                        with st.spinner(f"코스피 {labels_kr[i]} 실시간 데이터 스캔 중... (IP 차단 방어 모드)"):
                            time.sleep(2) 
                            try:
                                session = get_robust_session()[0]
                                data_1d_raw = yf.download(chunks_yf[i], period="2y", interval="1d", progress=False, session=session)
                                data_1h_raw = yf.download(chunks_yf[i], period="730d", interval="1h", progress=False, session=session)
                                
                                if 'Close' in data_1d_raw: data_1d = data_1d_raw['Close']
                                else: data_1d = data_1d_raw
                                if 'Close' in data_1h_raw: data_1h = data_1h_raw['Close']
                                else: data_1h = data_1h_raw
                                if isinstance(data_1d, pd.Series): data_1d = data_1d.to_frame(name=chunks_yf[i][0])
                                if isinstance(data_1h, pd.Series): data_1h = data_1h.to_frame(name=chunks_yf[i][0])
                                current_update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                
                                for j, yf_sym in enumerate(chunks_yf[i]):
                                    ui_sym = chunks_ui[i][j]
                                    if yf_sym not in data_1d.columns or yf_sym not in data_1h.columns: c_type, c_date, c_price = "데이터 부족", "-", "-"
                                    else:
                                        df_sym_1d = data_1d[yf_sym].dropna()
                                        df_sym_1h = data_1h[yf_sym].dropna()
                                        if len(df_sym_1d) < 150 or len(df_sym_1h) < 150: c_type, c_date, c_price = "상장기간 부족", "-", "-"
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
                                                c_price = f"₩{merged.loc[latest_idx, 'Close']:,.0f}"
                                            else:
                                                c_type, c_date, c_price = "최근 1년 내 크로스 없음", "-", "-"
                                    
                                    mask = st.session_state.kospi100_state_df['Symbol'] == ui_sym
                                    st.session_state.kospi100_state_df.loc[mask, '크로스 상태 (4H/1D EMA200)'] = c_type
                                    st.session_state.kospi100_state_df.loc[mask, '크로스 날짜'] = c_date
                                    st.session_state.kospi100_state_df.loc[mask, '크로스 당시 주가'] = c_price
                                    st.session_state.kospi100_state_df.loc[mask, '업데이트 날짜'] = current_update_time

                                st.success(f"✅ {current_update_time} 기준, 코스피 {labels_kr[i]} 크로스 분석 완료!")
                                st.rerun() 
                            except Exception as e:
                                st.error(f"야후 파이낸스 스캔 중 오류 발생 (잠시 후 다시 시도해주세요): {str(e)}")

            display_cols_kr = ['순위', '시총', 'Symbol', 'Name', '산업군(Industry)', '분야 순위', '크로스 상태 (4H/1D EMA200)', '크로스 날짜', '크로스 당시 주가', '업데이트 날짜']
            st.dataframe(st.session_state.kospi100_state_df[display_cols_kr], use_container_width=True, hide_index=True, height=1100)
