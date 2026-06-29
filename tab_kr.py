import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta, timezone
import yfinance as yf
import altair as alt
import streamlit.components.v1 as components
import xml.etree.ElementTree as ET

# 커스텀 히트맵을 위한 plotly (에러 방어용)
try:
    import plotly.express as px
except ImportError:
    px = None

# 💡 영우님의 나스닥 13개 핵심 테마를 한국 증시(코스피)에 완벽 적용한 매핑!
CUSTOM_KR_THEME_MAPPING = {
    # 1. 메모리·스토리지 / AI 반도체
    "005930": "메모리·스토리지", "000660": "메모리·스토리지", # 삼성전자, SK하이닉스
    "042700": "반도체 장비·EDA", "041510": "반도체 장비·EDA", # 한미반도체, 에스엠코어 등
    # 2. 빅테크·플랫폼 / 인터넷·이커머스
    "035420": "빅테크·플랫폼", "035720": "빅테크·플랫폼", "066570": "빅테크·플랫폼", # 네이버, 카카오, LG전자
    "032640": "통신·미디어·엔터", "017670": "통신·미디어·엔터", "030200": "통신·미디어·엔터", # LGU+, SKT, KT
    "352820": "통신·미디어·엔터", "035900": "통신·미디어·엔터", "259960": "통신·미디어·엔터", "036570": "통신·미디어·엔터", "251270": "통신·미디어·엔터", # 하이브, 크래프톤, 엔씨, 넷마블
    # 3. 에너지·모빌리티·핀테크·우주 (2차전지, 자동차, 금융, 방산, 조선, 화학 통합)
    "005380": "에너지·모빌리티·핀테크·우주", "000270": "에너지·모빌리티·핀테크·우주", "012330": "에너지·모빌리티·핀테크·우주", # 현대차, 기아, 모비스
    "373220": "에너지·모빌리티·핀테크·우주", "006400": "에너지·모빌리티·핀테크·우주", "051910": "에너지·모빌리티·핀테크·우주", # LG엔솔, 삼성SDI, LG화학
    "003670": "에너지·모빌리티·핀테크·우주", "247540": "에너지·모빌리티·핀테크·우주", "096770": "에너지·모빌리티·핀테크·우주", "010950": "에너지·모빌리티·핀테크·우주", "011170": "에너지·모빌리티·핀테크·우주", # 포스코퓨처엠, S-Oil, 롯데케미칼
    "105560": "에너지·모빌리티·핀테크·우주", "055550": "에너지·모빌리티·핀테크·우주", "086790": "에너지·모빌리티·핀테크·우주", "316140": "에너지·모빌리티·핀테크·우주", "000030": "에너지·모빌리티·핀테크·우주", # 5대 금융지주
    "032830": "에너지·모빌리티·핀테크·우주", "000810": "에너지·모빌리티·핀테크·우주", # 삼성생명, 삼성화재
    "012450": "에너지·모빌리티·핀테크·우주", "047810": "에너지·모빌리티·핀테크·우주", "069260": "에너지·모빌리티·핀테크·우주", # 한화에어로, KAI 등
    "010140": "에너지·모빌리티·핀테크·우주", "042660": "에너지·모빌리티·핀테크·우주", "329180": "에너지·모빌리티·핀테크·우주", "009540": "에너지·모빌리티·핀테크·우주", # 삼성중공업, 한화오션, HD현대중공업 (조선 모빌리티)
    "047050": "에너지·모빌리티·핀테크·우주", # 포스코인터내셔널(에너지)
    # 4. 헬스케어·바이오
    "207940": "헬스케어·바이오", "068270": "헬스케어·바이오", "000100": "헬스케어·바이오", "128940": "헬스케어·바이오", # 삼바, 셀트리온, 유한양행, 한미약품
    # 5. 필수소비·리테일
    "051900": "필수소비·리테일", "090430": "필수소비·리테일", "023530": "필수소비·리테일", "139480": "필수소비·리테일", # LG생건, 아모레, 롯데쇼핑, 이마트
    "000080": "필수소비·리테일", "004370": "필수소비·리테일", "033920": "필수소비·리테일", "097950": "필수소비·리테일", # 하이트진로, 농심, KT&G, CJ제일제당
    # 6. 산업·운송·B2B서비스 (건설, 철강, 지주사, 물류 등)
    "005490": "산업·운송·B2B서비스", "004020": "산업·운송·B2B서비스", "010130": "산업·운송·B2B서비스", # POSCO홀딩스, 현대제철, 고려아연
    "028260": "산업·운송·B2B서비스", "000120": "산업·운송·B2B서비스", "000210": "산업·운송·B2B서비스", "000720": "산업·운송·B2B서비스", # 삼성물산, CJ대한통운, DL이앤씨, 현대건설
    # 7. 데이터센터·전력 인프라
    "015760": "데이터센터·전력 인프라", "034020": "데이터센터·전력 인프라", "058650": "데이터센터·전력 인프라", # 한전, 두산에너빌리티, 세아제강지주
    "010120": "데이터센터·전력 인프라", "267260": "데이터센터·전력 인프라", "298040": "데이터센터·전력 인프라", # LS일렉트릭, HD현대일렉트릭, 효성중공업
    # 8. 소프트웨어·SaaS·보안 / 시스템·아날로그·통신 반도체
    "018260": "소프트웨어·SaaS·보안", "022100": "소프트웨어·SaaS·보안", # 삼성SDS, 포스코DX
    "009150": "시스템·아날로그·통신 반도체", "011070": "시스템·아날로그·통신 반도체", "243070": "시스템·아날로그·통신 반도체" # 삼성전기, LG이노텍, 솔루스첨단소재
}

# 💡 리스트에 없는 코스피 종목을 13개 테마로 밀어넣는 초강력 징검다리 딕셔너리 (미분류 제로화)
AUTO_SECTOR_MAPPING_KR = {
    "Commercial Banks": "에너지·모빌리티·핀테크·우주", "상업 은행": "에너지·모빌리티·핀테크·우주",
    "Finance/Rental/Leasing": "에너지·모빌리티·핀테크·우주", "금융/임대/리스": "에너지·모빌리티·핀테크·우주",
    "Financial Conglomerates": "에너지·모빌리티·핀테크·우주", "금융 대기업": "에너지·모빌리티·핀테크·우주",
    "Property/Casualty Insurance": "에너지·모빌리티·핀테크·우주", "재산/상해 보험": "에너지·모빌리티·핀테크·우주",
    "Life/Health Insurance": "에너지·모빌리티·핀테크·우주", "생명/건강 보험": "에너지·모빌리티·핀테크·우주",
    "Investment Banks/Brokers": "에너지·모빌리티·핀테크·우주", "투자 은행/브로커": "에너지·모빌리티·핀테크·우주",
    "Investment Trusts/Mutual Funds": "에너지·모빌리티·핀테크·우주", "투자 신탁/뮤추얼 펀드": "에너지·모빌리티·핀테크·우주",
    "Auto Manufacturing": "에너지·모빌리티·핀테크·우주", "자동차 제조": "에너지·모빌리티·핀테크·우주",
    "Motor Vehicles": "에너지·모빌리티·핀테크·우주", "모터 차량": "에너지·모빌리티·핀테크·우주",
    "Auto Parts: OEM": "에너지·모빌리티·핀테크·우주", "자동차 부품: OEM": "에너지·모빌리티·핀테크·우주",
    "Aerospace & Defense": "에너지·모빌리티·핀테크·우주", "항공우주 & 국방": "에너지·모빌리티·핀테크·우주",
    "Oil & Gas Production": "에너지·모빌리티·핀테크·우주", "석유 & 가스 생산": "에너지·모빌리티·핀테크·우주",
    "Oil Refining/Marketing": "에너지·모빌리티·핀테크·우주", "석유 정제/마케팅": "에너지·모빌리티·핀테크·우주",
    "Chemicals: Major Diversified": "에너지·모빌리티·핀테크·우주", "화학: 주요 다각화": "에너지·모빌리티·핀테크·우주",
    "Chemicals: Specialty": "에너지·모빌리티·핀테크·우주", "특수 화학": "에너지·모빌리티·핀테크·우주",
    "Wholesale Distributors": "산업·운송·B2B서비스", "도매 유통": "산업·운송·B2B서비스",
    "Steel": "산업·운송·B2B서비스", "철강": "산업·운송·B2B서비스",
    "Other Metals/Minerals": "산업·운송·B2B서비스", "기타 금속/광물": "산업·운송·B2B서비스",
    "Engineering & Construction": "산업·운송·B2B서비스", "엔지니어링 & 건설": "산업·운송·B2B서비스",
    "Homebuilding": "산업·운송·B2B서비스", "주택 건설": "산업·운송·B2B서비스",
    "Marine Shipping": "산업·운송·B2B서비스", "해상 운송": "산업·운송·B2B서비스",
    "Airlines": "산업·운송·B2B서비스", "항공사": "산업·운송·B2B서비스",
    "Industrial Machinery": "산업·운송·B2B서비스", "산업 기계": "산업·운송·B2B서비스",
    "Trucks/Construction/Farm Machinery": "산업·운송·B2B서비스", "트럭/건설/농기계": "산업·운송·B2B서비스",
    "Air Freight/Couriers": "산업·운송·B2B서비스", "항공 화물/택배": "산업·운송·B2B서비스",
    "Railroads": "산업·운송·B2B서비스", "철도": "산업·운송·B2B서비스",
    "Electric Utilities": "데이터센터·전력 인프라", "전기 유틸리티": "데이터센터·전력 인프라",
    "Electrical Products": "데이터센터·전력 인프라", "전기 제품": "데이터센터·전력 인프라",
    "Telecommunications Equipment": "빅테크·플랫폼", "통신 장비": "빅테크·플랫폼",
    "Consumer Electronics/Appliances": "빅테크·플랫폼", "소비자 가전": "빅테크·플랫폼",
    "Internet Software/Services": "빅테크·플랫폼", "인터넷 소프트웨어/서비스": "빅테크·플랫폼",
    "Packaged Software": "소프트웨어·SaaS·보안", "패키지 소프트웨어": "소프트웨어·SaaS·보안",
    "Information Technology Services": "소프트웨어·SaaS·보안", "정보 기술 서비스": "소프트웨어·SaaS·보안",
    "Semiconductors": "메모리·스토리지", "반도체": "메모리·스토리지",
    "Electronic Technology": "시스템·아날로그·통신 반도체", "전자 기술": "시스템·아날로그·통신 반도체",
    "Electronic Components": "시스템·아날로그·통신 반도체", "전자 부품": "시스템·아날로그·통신 반도체",
    "Electronic Equipment/Instruments": "시스템·아날로그·통신 반도체", "전자 장비/기기": "시스템·아날로그·통신 반도체",
    "Pharmaceuticals: Major": "헬스케어·바이오", "제약: 주요": "헬스케어·바이오",
    "Biotechnology": "헬스케어·바이오", "생명공학": "헬스케어·바이오",
    "Medical Specialties": "헬스케어·바이오", "의료 전문": "헬스케어·바이오",
    "Movies/Entertainment": "통신·미디어·엔터", "영화/엔터테인먼트": "통신·미디어·엔터",
    "Broadcasting": "통신·미디어·엔터", "방송": "통신·미디어·엔터",
    "Wireless Telecommunications": "통신·미디어·엔터", "무선 통신": "통신·미디어·엔터",
    "Publishing: Books/Magazines": "통신·미디어·엔터", "출판": "통신·미디어·엔터",
    "Advertising/Marketing Services": "통신·미디어·엔터", "광고/마케팅 서비스": "통신·미디어·엔터",
    "Apparel/Footwear": "필수소비·리테일", "의류/신발": "필수소비·리테일",
    "Household/Personal Care": "필수소비·리테일", "가정/개인 관리": "필수소비·리테일",
    "Food: Major Diversified": "필수소비·리테일", "식품: 주요 다각화": "필수소비·리테일",
    "Food: Specialty/Candy": "필수소비·리테일", "식품: 특수/캔디": "필수소비·리테일",
    "Beverages: Non-Alcoholic": "필수소비·리테일", "음료: 비알코올": "필수소비·리테일",
    "Beverages: Alcoholic": "필수소비·리테일", "음료: 알코올": "필수소비·리테일",
    "Tobacco": "필수소비·리테일", "담배": "필수소비·리테일",
    "Specialty Stores": "인터넷 플랫폼·이커머스·여행", "전문 상점": "인터넷 플랫폼·이커머스·여행",
    "Discount Stores": "필수소비·리테일", "할인점": "필수소비·리테일",
    "Internet Retail": "인터넷 플랫폼·이커머스·여행", "인터넷 소매": "인터넷 플랫폼·이커머스·여행"
}

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

def color_pct(val):
    if isinstance(val, str) and '%' in val:
        try:
            num = float(val.replace('%', '').replace('+', ''))
            color = '#ef4444' if num < 0 else '#22c55e'
            return f'color: {color}; font-weight: bold;'
        except: pass
    return ''

def render_kr_map_tab():
    if "kospi100_state_df" not in st.session_state:
        st.session_state.kospi100_state_df = pd.DataFrame()

    st.markdown("### 🇰🇷 한국 코스피 상위 Top 200 주도주 맵 (나스닥 13대 테마 연동)")
    st.info("💡 **알림:** 실시간 트레이딩뷰(TradingView) 서버에서 진성 코스피 시가총액 200위 명단을 스캔하여 영우님의 13대 글로벌 테마로 묶어냅니다.")

    if not st.session_state.kospi100_state_df.empty and len(st.session_state.kospi100_state_df) <= 100:
        st.warning("⚠️ **시스템 업그레이드 알림:** 코스피 스캔 범위가 200위로 확장되었습니다! 메모리에 예전 100위 데이터가 남아있으므로, 반드시 아래의 빨간색 **[스캔 시작]** 버튼을 다시 눌러 데이터를 갱신해주세요.")

    if st.button("🔄 실시간 순수 코스피 Top 200 스캔 시작", type="primary", key="btn_kr_scan"):
        with st.spinner("코스피 전 종목을 스캔하여 실시간 시총 200위를 선별 중입니다... (약 2초 소요)"):
            try:
                url = "https://scanner.tradingview.com/korea/scan"
                payload = {
                    "filter": [
                        {"left": "market_cap_basic", "operation": "nempty"},
                        {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
                        {"left": "exchange", "operation": "in_range", "right": ["KRX"]} 
                    ],
                    "options": {"lang": "ko"},
                    "markets": ["korea"],
                    "symbols": {"query": {"types": []}, "tickers": []},
                    "columns": ["name", "description", "sector", "industry", "market_cap_basic", "close", "change", "Perf.W", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y", "RSI"],
                    "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                    "range": [0, 400] 
                }
                headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
                res = requests.post(url, json=payload, headers=headers)
                
                if res.status_code != 200: raise Exception(f"트레이딩뷰 서버 응답 지연 (상태 코드: {res.status_code})")
                data = res.json()
                
                df_list = []
                seen_tickers = set()
                
                for item in data.get('data', []):
                    # 💡 200개 종목 추출 로직 적용!
                    if len(df_list) >= 200: break
                    
                    sym = item['d'][0] 
                    name_raw = item['d'][1]
                    ind_raw = item['d'][3]
                    mcap = item['d'][4]
                    close_p = item['d'][5]
                    chg_1d = item['d'][6]
                    chg_1w = item['d'][7]
                    chg_1m = item['d'][8]
                    chg_3m = item['d'][9]  
                    chg_6m = item['d'][10] 
                    chg_1y = item['d'][11] 
                    rsi_val = item['d'][12]
                    
                    base_ticker = sym.split(':')[-1]
                    
                    # 우선주 필터링
                    if len(base_ticker) == 6 and not base_ticker.endswith('0'): continue
                    if "우" in name_raw and ("우B" in name_raw or "우(" in name_raw or name_raw.endswith("우")): continue
                    
                    if base_ticker in seen_tickers: continue
                    seen_tickers.add(base_ticker)
                    yf_ticker = f"{base_ticker}.KS"
                    
                    # 💡 한국 증시를 나스닥 테마로 매핑!
                    if base_ticker in CUSTOM_KR_THEME_MAPPING:
                        ind_trans = CUSTOM_KR_THEME_MAPPING[base_ticker]
                    else:
                        closest_sector = AUTO_SECTOR_MAPPING_KR.get(ind_raw, "기타 (KOSPI 미분류)")
                        ind_trans = f"{closest_sector} 🤖" if closest_sector != "기타 (KOSPI 미분류)" else "기타 (KOSPI 미분류) 🤖"
                    
                    if rsi_val: rsi_str = f"🚨 {rsi_val:.1f}" if rsi_val < 25 else f"{rsi_val:.1f}"
                    else: rsi_str = "-"
                    
                    df_list.append({
                        '순위': len(df_list) + 1,
                        'Symbol': base_ticker,
                        'YF_Symbol': yf_ticker,
                        'Name': name_raw,
                        '시총': format_krw_direct(mcap),
                        '산업군(Industry)': ind_trans,
                        '분야 순위': "-",
                        '현재주가': f"₩{close_p:,.0f}" if close_p else "-",
                        'RSI': rsi_str,
                        '1일 변동': f"{chg_1d:+.2f}%" if chg_1d else "-",
                        '7일 변동': f"{chg_1w:+.2f}%" if chg_1w else "-",
                        '30일 변동': f"{chg_1m:+.2f}%" if chg_1m else "-",
                        '60일 변동': f"{chg_3m:+.2f}%" if chg_3m else "-",
                        '120일 변동': f"{chg_6m:+.2f}%" if chg_6m else "-",
                        '200일 변동': f"{chg_1y:+.2f}%" if chg_1y else "-",
                        '시가총액_num': mcap,
                        '1일_변동_num': chg_1d if chg_1d is not None else 0.0, # 히트맵용
                        '크로스 상태 (4H/1D EMA200)': "대기 중",
                        '크로스 날짜': "-",
                        '크로스 당시 주가': "-",
                        '업데이트 날짜': "-"
                    })
                
                new_df = pd.DataFrame(df_list)
                new_df['분야 순위'] = new_df.groupby('산업군(Industry)')['시가총액_num'].rank(ascending=False, method='min').apply(lambda x: f"테마 {int(x)}위")
                st.session_state.kospi100_state_df = new_df
                st.success("✅ 실시간 코스피 시총 Top 200 리스트 업데이트 완료! (영우님의 13대 테마 100% 적용)")
            except Exception as e:
                st.error(f"데이터 스캔 중 오류가 발생했습니다: {e}")

    # 200개 데이터가 있으면 코스피 전용 커스텀 히트맵 렌더링!
    if not st.session_state.kospi100_state_df.empty and len(st.session_state.kospi100_state_df) > 100:
        st.markdown("#### 🗺️ 커스텀 코스피 주도주 히트맵 (나스닥 13대 테마 분류)")
        st.caption("💡 아래 표에 스캔된 200개 종목을 영우님의 맞춤형 나스닥 테마로 재분류하여 그려낸 **'한국 증시 자금 흐름 히트맵'**입니다.")
        
        if px is not None:
            hm_df = st.session_state.kospi100_state_df.copy()
            fig = px.treemap(
                hm_df,
                path=[px.Constant("🇰🇷 한국 주식 시장 (Top 200)"), '산업군(Industry)', 'Name'],
                values='시가총액_num',
                color='1일_변동_num',
                color_continuous_scale=['#f23645', '#434651', '#089981'], 
                color_continuous_midpoint=0,
                range_color=[-5, 5], # 💡 코스피도 이상치 방어(-5%~+5%) 적용!
                custom_data=['Symbol', '현재주가', '1일 변동'] 
            )
            
            # 히트맵 글씨 디자인 및 세로 길이 1200으로 시원하게 확장!
            fig.update_traces(
                textinfo="label+text",
                texttemplate="<b><span style='font-size: 26px;'>%{label}</span></b><br><br><b><span style='font-size: 18px;'>%{customdata[2]}</span></b>", 
                hovertemplate="<b>%{label} (%{customdata[0]})</b><br>테마: %{parent}<br>현재가: %{customdata[1]}<br>1일 변동: %{customdata[2]}<extra></extra>"
            )
            fig.update_layout(
                margin=dict(t=30, l=10, r=10, b=10), 
                height=1200, 
                font=dict(family="Arial Black, sans-serif")
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("🚨 커스텀 히트맵을 렌더링하기 위한 'plotly' 파이썬 패키지가 설치되어 있지 않습니다.")
            
        st.markdown("---")

        st.markdown("#### 📈 코스피(KOSPI) 기간별 수익률 지표")
        try:
            # 💡 야후 통신망(주말 딜레이 버그)을 완벽히 버리고 네이버 금융 백그라운드 API 우회 호출!
            url = "https://fchart.stock.naver.com/sise.nhn?symbol=KOSPI&timeframe=day&count=1500&requestType=0"
            res = requests.get(url)
            root = ET.fromstring(res.text)
            items = root.findall('.//item')
            data = []
            for item in items:
                row = item.attrib['data'].split('|')
                data.append({
                    'Date': pd.to_datetime(row[0]),
                    'Close': float(row[4])
                })
            
            if data:
                kospi_df = pd.DataFrame(data).set_index('Date')
                close_series = kospi_df['Close'].dropna()
                
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
            else: 
                st.warning("네이버 금융 통신망 일시 지연. 새로고침을 눌러주세요.")
        except Exception as e: 
            st.error(f"데이터를 불러오는 중 오류 발생: {e}")
            
        st.markdown("#### 📊 코스피 (KOSPI) 최근 1년 흐름 (일봉 자체 캔들 차트)")
        try:
            # 💡 야후 통신망(주말 딜레이 버그)을 완벽히 버리고 네이버 금융 백그라운드 API 우회 호출!
            url = "https://fchart.stock.naver.com/sise.nhn?symbol=KOSPI&timeframe=day&count=365&requestType=0"
            res = requests.get(url)
            root = ET.fromstring(res.text)
            items = root.findall('.//item')
            data = []
            for item in items:
                row = item.attrib['data'].split('|')
                data.append({
                    'Date': pd.to_datetime(row[0]),
                    'Open': float(row[1]),
                    'High': float(row[2]),
                    'Low': float(row[3]),
                    'Close': float(row[4]),
                    'Volume': float(row[5])
                })
            
            if data:
                df_chart = pd.DataFrame(data)
                
                # RSI 계산 (14일)
                delta = df_chart['Close'].diff()
                gain = (delta.where(delta > 0, 0)).fillna(0)
                loss = (-delta.where(delta < 0, 0)).fillna(0)
                avg_gain = gain.rolling(window=14).mean()
                avg_loss = loss.rolling(window=14).mean()
                rs = avg_gain / avg_loss
                df_chart['RSI'] = 100 - (100 / (1 + rs))

                # 색상 조건
                color_condition = alt.condition("datum.Open <= datum.Close", alt.value("#089981"), alt.value("#f23645"))
                
                # 차트 상/하단 여백 최소화를 위한 최저/최고가 계산
                min_price = df_chart['Low'].min() * 0.98
                max_price = df_chart['High'].max() * 1.02
                
                # 마우스 오버(Hover) 시 세로줄과 툴팁을 동기화하기 위한 선택 객체
                hover = alt.selection_point(fields=['Date'], nearest=True, on='mouseover', empty=False, clear='mouseout')

                # X축 (상단/중단 차트는 숨기고, 하단 차트에서만 표시)
                x_axis_hidden = alt.X('Date:O', axis=alt.Axis(labels=False, ticks=False, domain=False, title=None))
                x_axis_show = alt.X('Date:O', 
                        title=None, 
                        axis=alt.Axis(
                            labelAngle=0, 
                            labelColor='#787b86',
                            labelExpr="indexof(datum.label, datum.value) % 20 == 0 ? timeFormat(datum.value, '%Y-%m-%d') : ''",
                            grid=True,
                            gridColor='#e0e3eb',
                            gridDash=[2, 2],
                            domain=False,
                            ticks=False
                        ))
                
                base = alt.Chart(df_chart)

                # 공통 툴팁 및 크로스헤어 레이어
                selectors = base.mark_point(size=100).encode(
                    x=x_axis_hidden, opacity=alt.value(0),
                    tooltip=[
                        alt.Tooltip('Date:T', format='%Y-%m-%d', title='날짜'),
                        alt.Tooltip('Open:Q', format=',.0f', title='시가'),
                        alt.Tooltip('High:Q', format=',.0f', title='고가'),
                        alt.Tooltip('Low:Q', format=',.0f', title='저가'),
                        alt.Tooltip('Close:Q', format=',.0f', title='종가'),
                        alt.Tooltip('Volume:Q', format=',.0f', title='거래량'),
                        alt.Tooltip('RSI:Q', format='.2f', title='RSI')
                    ]
                ).add_params(hover)

                # 마우스를 따라다니는 공통 세로선
                rules = base.mark_rule(color='#787b86', strokeWidth=1, strokeDash=[5,5]).encode(
                    x=x_axis_hidden
                ).transform_filter(hover)
                
                # 1. 캔들 차트 (높이 750)
                rule_candle = base.mark_rule(size=2.0).encode(
                    x=x_axis_hidden,
                    y=alt.Y('Low:Q', title=None, scale=alt.Scale(domain=[min_price, max_price]), axis=alt.Axis(orient='right', format=',.0f', labelFontSize=12)),
                    y2='High:Q',
                    color=color_condition
                )
                bar_candle = base.mark_bar(size=5.0).encode(
                    x=x_axis_hidden,
                    y='Open:Q',
                    y2='Close:Q',
                    color=color_condition
                )
                candlestick = (rule_candle + bar_candle + selectors + rules).properties(height=750)
                
                # 2. 거래량 차트 (높이 150)
                volume_bar = base.mark_bar(size=5.0).encode(
                    x=x_axis_hidden,
                    y=alt.Y('Volume:Q', title=None, axis=alt.Axis(orient='right', format='.2s', labelFontSize=12)),
                    color=color_condition
                )
                volume_chart = (volume_bar + selectors + rules).properties(height=150)

                # 3. RSI 차트 (하단에 X축 날짜 표시)
                rsi_line = base.mark_line(color='#673ab7', strokeWidth=2).encode(
                    x=x_axis_show,
                    y=alt.Y('RSI:Q', title='RSI', scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(orient='right', labelFontSize=12))
                )
                rsi_baseline = alt.Chart(pd.DataFrame({'y': [30, 70]})).mark_rule(strokeDash=[5,5], color='gray').encode(y='y')
                rsi_chart = (rsi_line + rsi_baseline + selectors.encode(x=x_axis_show) + rules.encode(x=x_axis_show)).properties(height=150)
                
                # 차트 세로 결합 (테두리 및 스페이싱 제거)
                combined = alt.vconcat(candlestick, volume_chart, rsi_chart, spacing=0).resolve_scale(x='shared').configure_view(
                    stroke='lightgray', strokeWidth=1 
                ).configure_axis(
                    labelFontSize=14
                )

                st.altair_chart(combined, use_container_width=True)
                
            else:
                st.warning("네이버 금융 통신망 지연으로 차트를 불러오지 못했습니다. (새로고침을 눌러주세요)")
        except Exception as e:
            st.error(f"차트 데이터 오류 발생: {e}")
            
        st.markdown("---")

        yf_symbols = st.session_state.kospi100_state_df['YF_Symbol'].tolist()
        ui_symbols = st.session_state.kospi100_state_df['Symbol'].tolist()
        
        # 💡 코스피도 나스닥과 동일하게 50개씩 4개의 덩어리로 버튼 재구성!
        chunks_yf = [yf_symbols[i:i+50] for i in range(0, 200, 50)]
        chunks_ui = [ui_symbols[i:i+50] for i in range(0, 200, 50)]
        labels_kr = ["1위~50위", "51위~100위", "101위~150위", "151위~200위"]
        
        st.caption("야후 파이낸스 데이터 차단(Rate Limit)을 방지하기 위해 50개 종목씩 나누어 '4시간봉 EMA 200 vs 1일봉 EMA 200' 크로스 현황을 정밀 스캔합니다.")
        cols_kr = st.columns(4)
        for i in range(4):
            if i < len(chunks_yf):
                if cols_kr[i].button(f"🚀 코스피 {labels_kr[i]} 스캔", use_container_width=True, key=f"btn_kr_{i}"):
                    with st.spinner(f"코스피 {labels_kr[i]} 실시간 데이터 스캔 중... (IP 차단 방어 모드)"):
                        try:
                            data_1d_raw = yf.download(chunks_yf[i], period="2y", interval="1d", progress=False)
                            data_1h_raw = yf.download(chunks_yf[i], period="730d", interval="1h", progress=False)
                            
                            if 'Close' in data_1d_raw: data_1d = data_1d_raw['Close']
                            else: data_1d = data_1d_raw
                            if 'Close' in data_1h_raw: data_1h = data_1h_raw['Close']
                            else: data_1h = data_1h_raw
                            if isinstance(data_1d, pd.Series): data_1d = data_1d.to_frame(name=chunks_yf[i][0])
                            if isinstance(data_1h, pd.Series): data_1h = data_1h.to_frame(name=chunks_yf[i][0])
                            current_update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            
                            for j, yf_sym in enumerate(chunks_yf[i]):
                                ui_sym = chunks_ui[i][j]
                                if yf_sym not in data_1d.columns or yf_sym not in data_1h.columns: 
                                    c_type, c_date, c_price = "데이터 부족", "-", "-"
                                else:
                                    df_sym_1d = data_1d[yf_sym].dropna()
                                    df_sym_1h = data_1h[yf_sym].dropna()
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

        display_cols_kr = [
            '순위', 'Symbol', '시총', 'Name', '분야 순위', '현재주가', 'RSI', 
            '1일 변동', '7일 변동', '30일 변동', '60일 변동', '120일 변동', '200일 변동', 
            '산업군(Industry)', '크로스 상태 (4H/1D EMA200)', '크로스 날짜', '크로스 당시 주가', '업데이트 날짜'
        ]
        
        st.dataframe(
            st.session_state.kospi100_state_df[display_cols_kr].style.map(color_pct, subset=['1일 변동', '7일 변동', '30일 변동', '60일 변동', '120일 변동', '200일 변동']),
            column_config={
                "순위": st.column_config.NumberColumn(width="small"),
                "Symbol": st.column_config.TextColumn("심볼", width="small"),
                "시총": st.column_config.TextColumn("시총", width="small"),
                "Name": st.column_config.TextColumn("Name", width="medium"),
                "분야 순위": st.column_config.TextColumn("테마순위", width="small"),
                "현재주가": st.column_config.TextColumn("현재가", width="small"),
                "RSI": st.column_config.TextColumn("RSI", width="small"),
                "1일 변동": st.column_config.TextColumn("1일", width="small"),
                "7일 변동": st.column_config.TextColumn("7일", width="small"),
                "30일 변동": st.column_config.TextColumn("30일", width="small"),
                "60일 변동": st.column_config.TextColumn("60일", width="small"),
                "120일 변동": st.column_config.TextColumn("120일", width="small"),
                "200일 변동": st.column_config.TextColumn("200일", width="small"),
                "산업군(Industry)": st.column_config.TextColumn("분류(테마)", width="medium"),
                "크로스 상태 (4H/1D EMA200)": st.column_config.TextColumn("EMA크로스", width="small"),
                "크로스 날짜": st.column_config.TextColumn("크로스날짜", width="small"),
                "크로스 당시 주가": st.column_config.TextColumn("크로스가", width="small"),
                "업데이트 날짜": st.column_config.TextColumn("업데이트", width="small")
            },
            use_container_width=True, 
            hide_index=True, 
            height=1100
        )
