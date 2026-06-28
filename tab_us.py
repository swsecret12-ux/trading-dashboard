import streamlit as st
import pandas as pd
import requests
import re
import time
from datetime import datetime, timezone
import yfinance as yf
import streamlit.components.v1 as components

# 커스텀 히트맵을 위한 plotly (에러 방어용)
try:
    import plotly.express as px
except ImportError:
    px = None

# 💡 영우님이 직접 설계하신 나스닥 핵심 테마 매핑 딕셔너리
CUSTOM_US_THEME_MAPPING = {
    "NVDA": "AI 반도체·네트워크", "AVGO": "AI 반도체·네트워크", "AMD": "AI 반도체·네트워크", "CSCO": "AI 반도체·네트워크", "ARM": "AI 반도체·네트워크", "MRVL": "AI 반도체·네트워크", "ALAB": "AI 반도체·네트워크", "LITE": "AI 반도체·네트워크",
    "ASML": "반도체 장비·EDA", "AMAT": "반도체 장비·EDA", "LRCX": "반도체 장비·EDA", "KLAC": "반도체 장비·EDA", "CDNS": "반도체 장비·EDA", "SNPS": "반도체 장비·EDA", "TER": "반도체 장비·EDA",
    "MU": "메모리·스토리지", "SNDK": "메모리·스토리지", "STX": "메모리·스토리지", "WDC": "메모리·스토리지",
    "INTC": "시스템·아날로그·통신 반도체", "TXN": "시스템·아날로그·통신 반도체", "QCOM": "시스템·아날로그·통신 반도체", "ADI": "시스템·아날로그·통신 반도체", "NXPI": "시스템·아날로그·통신 반도체", "MPWR": "시스템·아날로그·통신 반도체", "MCHP": "시스템·아날로그·통신 반도체",
    "AAPL": "빅테크·플랫폼", "MSFT": "빅테크·플랫폼", "AMZN": "빅테크·플랫폼", "GOOGL": "빅테크·플랫폼", "GOOG": "빅테크·플랫폼", "META": "빅테크·플랫폼",
    "PLTR": "소프트웨어·SaaS·보안", "PANW": "소프트웨어·SaaS·보안", "CRWD": "소프트웨어·SaaS·보안", "APP": "소프트웨어·SaaS·보안", "FTNT": "소프트웨어·SaaS·보안", "DDOG": "소프트웨어·SaaS·보안", "ADBE": "소프트웨어·SaaS·보안", "INTU": "소프트웨어·SaaS·보안", "ADSK": "소프트웨어·SaaS·보안", "WDAY": "소프트웨어·SaaS·보안",
    "CEG": "데이터센터·전력 인프라", "AEP": "데이터센터·전력 인프라", "NBIS": "데이터센터·전력 인프라", "CRWV": "데이터센터·전력 인프라", "XEL": "데이터센터·전력 인프라", "EXC": "데이터센터·전력 인프라",
    "NFLX": "통신·미디어·엔터", "TMUS": "통신·미디어·엔터", "CMCSA": "통신·미디어·엔터", "WBD": "통신·미디어·엔터", "EA": "통신·미디어·엔터", "TTWO": "통신·미디어·엔터",
    "SHOP": "인터넷 플랫폼·이커머스·여행", "BKNG": "인터넷 플랫폼·이커머스·여행", "PDD": "인터넷 플랫폼·이커머스·여행", "MAR": "인터넷 플랫폼·이커머스·여행", "ABNB": "인터넷 플랫폼·이커머스·여행", "MELI": "인터넷 플랫폼·이커머스·여행", "DASH": "인터넷 플랫폼·이커머스·여행",
    "AMGN": "헬스케어·바이오", "GILD": "헬스케어·바이오", "ISRG": "헬스케어·바이오", "VRTX": "헬스케어·바이오", "REGN": "헬스케어·바이오", "IDXX": "헬스케어·바이오", "ALNY": "헬스케어·바이오", "GEHC": "헬스케어·바이오", "DXCM": "헬스케어·바이오",
    "WMT": "필수소비·리테일", "COST": "필수소비·리테일", "PEP": "필수소비·리테일", "SBUX": "필수소비·리테일", "MNST": "필수소비·리테일", "MDLZ": "필수소비·리테일", "ORLY": "필수소비·리테일", "ROST": "필수소비·리테일", "KDP": "필수소비·리테일", "CCEP": "필수소비·리테일", "KHC": "필수소비·리테일",
    "LIN": "산업·운송·B2B서비스", "HON": "산업·운송·B2B서비스", "CSX": "산업·운송·B2B서비스", "ADP": "산업·운송·B2B서비스", "CTAS": "산업·운송·B2B서비스", "PCAR": "산업·운송·B2B서비스", "FAST": "산업·운송·B2B서비스", "FER": "산업·운송·B2B서비스", "ODFL": "산업·운송·B2B서비스", "AXON": "산업·운송·B2B서비스", "TRI": "산업·운송·B2B서비스", "PAYX": "산업·운송·B2B서비스", "ROP": "산업·운송·B2B서비스", "CPRT": "산업·운송·B2B서비스",
    "TSLA": "에너지·모빌리티·핀테크·우주", "BKR": "에너지·모빌리티·핀테크·우주", "RKLB": "에너지·모빌리티·핀테크·우주", "FANG": "에너지·모빌리티·핀테크·우주", "PYPL": "에너지·모빌리티·핀테크·우주", "MSTR": "에너지·모빌리티·핀테크·우주"
}

# 💡 리스트에 없는 종목을 만났을 때 AI가 대신 배정해줄 징검다리 딕셔너리
AUTO_SECTOR_MAPPING = {
    "Semiconductors": "시스템·아날로그·통신 반도체", "Computer Processing Hardware": "AI 반도체·네트워크", "Computer Communications": "AI 반도체·네트워크",
    "Electronic Equipment/Instruments": "산업·운송·B2B서비스", "Packaged Software": "소프트웨어·SaaS·보안", "Internet Software/Services": "소프트웨어·SaaS·보안", 
    "Information Technology Services": "소프트웨어·SaaS·보안", "Internet Retail": "인터넷 플랫폼·이커머스·여행", "Apparel/Footwear Retail": "필수소비·리테일",
    "Specialty Stores": "필수소비·리테일", "Discount Stores": "필수소비·리테일", "Pharmaceuticals: Major": "헬스케어·바이오",
    "Biotechnology": "헬스케어·바이오", "Medical Specialties": "헬스케어·바이오", "Managed Health Care": "헬스케어·바이오",
    "Major Banks": "에너지·모빌리티·핀테크·우주", "Regional Banks": "에너지·모빌리티·핀테크·우주", "Investment Banks/Brokers": "에너지·모빌리티·핀테크·우주", 
    "Finance/Rental/Leasing": "에너지·모빌리티·핀테크·우주", "Property/Casualty Insurance": "에너지·모빌리티·핀테크·우주", "Life/Health Insurance": "헬스케어·바이오", 
    "Real Estate Investment Trusts": "산업·운송·B2B서비스", "Broadcasting": "통신·미디어·엔터", "Movies/Entertainment": "통신·미디어·엔터", 
    "Auto Manufacturing": "에너지·모빌리티·핀테크·우주", "Motor Vehicles": "에너지·모빌리티·핀테크·우주", "Aerospace & Defense": "에너지·모빌리티·핀테크·우주", 
    "Air Freight/Couriers": "산업·운송·B2B서비스", "Integrated Oil": "에너지·모빌리티·핀테크·우주", "Electric Utilities": "데이터센터·전력 인프라", 
    "Beverages: Non-Alcoholic": "필수소비·리테일", "Restaurants": "필수소비·리테일", "Household/Personal Care": "필수소비·리테일", 
    "Industrial Machinery": "산업·운송·B2B서비스", "Specialty Telecommunications": "AI 반도체·네트워크", "Computer Peripherals": "AI 반도체·네트워크", 
    "Investment Managers": "에너지·모빌리티·핀테크·우주", "Other Metals/Minerals": "산업·운송·B2B서비스", "Trucks/Construction/Farm Machinery": "산업·운송·B2B서비스"
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

def color_pct(val):
    if isinstance(val, str) and '%' in val:
        try:
            num = float(val.replace('%', '').replace('+', ''))
            color = '#ef4444' if num < 0 else '#22c55e'
            return f'color: {color}; font-weight: bold;'
        except: pass
    return ''

def render_us_map_tab():
    if "sp100_state_df" not in st.session_state:
        st.session_state.sp100_state_df = pd.DataFrame()

    st.markdown("### 🇺🇸 미국 시총 상위 Top 200 주도주 맵 (커스텀 테마 반영)")
    st.info("💡 **알림:** 실시간 트레이딩뷰(TradingView) 서버에서 진성 미국 시가총액 200위 명단을 스캔하여 영우님만의 테마로 묶어냅니다.")

    # 💡 100개짜리 옛날 데이터가 캐시에 남아있으면 경고를 띄워 스캔을 유도합니다!
    if not st.session_state.sp100_state_df.empty and len(st.session_state.sp100_state_df) <= 100:
        st.warning("⚠️ **시스템 업그레이드 알림:** 미국 시장 스캔 범위가 200위로 확장되었습니다! 메모리에 예전 100위 데이터가 남아있으므로, 반드시 아래의 빨간색 **[스캔 시작]** 버튼을 다시 눌러 데이터를 갱신해주세요.")

    if st.button("🔄 실시간 순수 미국 시총 Top 200 스캔 시작", type="primary", key="us_btn"):
        with st.spinner("미국 시장 전 종목을 스캔하여 실시간 시총 200위를 선별 중입니다... (약 2초 소요)"):
            try:
                url = "https://scanner.tradingview.com/america/scan"
                payload = {
                    "filter": [
                        {"left": "market_cap_basic", "operation": "nempty"},
                        {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
                        {"left": "exchange", "operation": "in_range", "right": ["AMEX", "NASDAQ", "NYSE"]} 
                    ],
                    "options": {"lang": "en"},
                    "markets": ["america"],
                    "symbols": {"query": {"types": []}, "tickers": []},
                    "columns": ["name", "description", "sector", "industry", "market_cap_basic", "close", "change", "Perf.W", "Perf.1M", "Perf.3M", "Perf.6M", "Perf.Y", "RSI"],
                    "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                    "range": [0, 400] # 충분한 범위로 넉넉하게 요청
                }
                headers = {"User-Agent": "Mozilla/5.0"}
                res = requests.post(url, json=payload, headers=headers)
                data = res.json()
                
                df_list = []
                seen_tickers = set()
                target_exact = ['JPM', 'ORCL', 'BAC', 'MS', 'GS', 'WFC', 'C']
                
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
                    name_trans = NAME_TRANSLATIONS.get(sym_clean, name_raw) 
                    
                    # 💡 영우 님이 정리해주신 커스텀 테마 매핑 우선 적용!
                    if sym_clean in CUSTOM_US_THEME_MAPPING:
                        ind_trans = CUSTOM_US_THEME_MAPPING[sym_clean]
                    else:
                        closest_sector = AUTO_SECTOR_MAPPING.get(ind_raw, "기타 (AI 미분류)")
                        ind_trans = f"{closest_sector} 🤖"
                    
                    if rsi_val: rsi_str = f"🚨 {rsi_val:.1f}" if rsi_val < 25 else f"{rsi_val:.1f}"
                    else: rsi_str = "-"
                    
                    df_list.append({
                        '순위': len(df_list) + 1,
                        'Symbol': sym_clean,
                        '시총': format_mcap_krw(mcap),
                        'Name': name_trans,
                        '산업군(Industry)': ind_trans,
                        '분야 순위': "-",
                        '현재주가': f"${close_p:,.2f}" if close_p else "-",
                        'RSI': rsi_str,
                        '1일 변동': f"{chg_1d:+.2f}%" if chg_1d else "-",
                        '7일 변동': f"{chg_1w:+.2f}%" if chg_1w else "-",
                        '30일 변동': f"{chg_1m:+.2f}%" if chg_1m else "-",
                        '60일 변동': f"{chg_3m:+.2f}%" if chg_3m else "-",
                        '120일 변동': f"{chg_6m:+.2f}%" if chg_6m else "-",
                        '200일 변동': f"{chg_1y:+.2f}%" if chg_1y else "-",
                        '시가총액_num': mcap,
                        '1일_변동_num': chg_1d if chg_1d is not None else 0.0, # 히트맵용 순수 숫자 데이터 보존
                        '크로스 상태 (4H/1D EMA200)': "대기 중",
                        '크로스 날짜': "-",
                        '크로스 당시 주가': "-"
                    })
                
                new_df = pd.DataFrame(df_list)
                new_df['분야 순위'] = new_df.groupby('산업군(Industry)')['시가총액_num'].rank(ascending=False, method='min').apply(lambda x: f"테마 {int(x)}위")
                st.session_state.sp100_state_df = new_df
                st.success("✅ 실시간 미국 시총 Top 200 리스트 업데이트 완료! (영우님의 커스텀 테마 100% 적용)")
            except Exception as e:
                st.error(f"데이터 스캔 중 오류가 발생했습니다: {e}")

    # 200개 데이터가 정상적으로 스캔되어 있다면 차트와 표를 그립니다.
    if not st.session_state.sp100_state_df.empty and len(st.session_state.sp100_state_df) > 100:
        # 💡 기존 트레이딩뷰 위젯을 버리고 Plotly 로 나만의 커스텀 히트맵 창조!
        st.markdown("#### 🗺️ 커스텀 미국 주도주 히트맵 (영우님 전용 섹터 기반)")
        st.caption("💡 아래 표에 스캔된 200개 종목을 영우님의 맞춤형 테마로 분류하여 직접 그려낸 **'나만의 자금 흐름 히트맵'**입니다. (상자 크기=시가총액, 색상=1일 변동률)")
        
        if px is not None:
            hm_df = st.session_state.sp100_state_df.copy()
            # 히트맵 생성 (Treemap)
            fig = px.treemap(
                hm_df,
                path=[px.Constant("🇺🇸 미국 주식 시장 (Top 200)"), '산업군(Industry)', 'Symbol'],
                values='시가총액_num',
                color='1일_변동_num',
                color_continuous_scale=['#f23645', '#434651', '#089981'], # 하락 빨간색, 0 회색, 상승 초록색
                color_continuous_midpoint=0,
                custom_data=['Name', '현재주가', '1일 변동'] # 툴팁용 추가 데이터
            )
            
            # 박스 내부 텍스트와 마우스 오버 툴팁 디자인 설정
            fig.update_traces(
                textinfo="label+text",
                texttemplate="<span style='font-size: 16px; font-weight: bold;'>%{label}</span><br>%{customdata[2]}", 
                hovertemplate="<b>%{label} (%{customdata[0]})</b><br>테마: %{parent}<br>현재가: %{customdata[1]}<br>1일 변동: %{customdata[2]}<extra></extra>"
            )
            fig.update_layout(margin=dict(t=30, l=10, r=10, b=10), height=700)
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("🚨 커스텀 히트맵을 렌더링하기 위한 'plotly' 파이썬 패키지가 설치되어 있지 않습니다. 터미널에 `pip install plotly`를 입력하시고, 배포 환경이라면 `requirements.txt`에 `plotly`를 꼭 추가해주세요.")
            
        st.markdown("---")
        
        st.markdown("#### 📈 나스닥 100 기간별 수익률 지표")
        try:
            sp500_df = pd.DataFrame()
            for tkr in ["^NDX", "QQQ"]:
                for _ in range(2):
                    try:
                        temp_df = yf.download(tkr, period="4y", interval="1d", progress=False)
                        if not temp_df.empty:
                            sp500_df = temp_df
                            break
                    except: time.sleep(1)
                if not sp500_df.empty: break

            if not sp500_df.empty:
                if isinstance(sp500_df.columns, pd.MultiIndex): close_series = sp500_df['Close'].iloc[:, 0].dropna()
                else: close_series = sp500_df['Close'].dropna()
                
                curr = close_series.iloc[-1]
                def ret(days):
                    if len(close_series) > days: return float((curr - close_series.iloc[-(days+1)]) / close_series.iloc[-(days+1)] * 100)
                    return 0.0
                    
                ndx_data = {"1일": ret(1), "7일": ret(5), "1개월": ret(21), "3개월": ret(63), "6개월": ret(126), "1년": ret(252), "3년": ret(756)}
                ndx_df = pd.DataFrame([ndx_data])
                
                formatted_df = ndx_df.map(lambda x: f"{x:+.2f}%" if isinstance(x, (int, float)) else x)
                st.dataframe(formatted_df.style.map(lambda x: color_pct(str(x))), use_container_width=True, hide_index=True)
            else: st.warning("야후 파이낸스 통신망 일시 지연. 새로고침을 눌러주세요.")
        except Exception as e: st.error(f"데이터를 불러오는 중 오류 발생: {e}")
            
        st.markdown("---")

        st.markdown("#### 📊 나스닥 100 (US TECH 100 CASH) 최근 1년 흐름 (일봉 실시간 차트)")
        
        tv_widget_us = """
        <div class="tradingview-widget-container" style="height:750px;width:100%; margin-bottom: 20px;">
          <div id="tradingview_ndx" style="height:calc(100% - 32px);width:100%"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({
          "autosize": true,
          "symbol": "OANDA:NAS100USD",
          "interval": "D",
          "timezone": "Etc/UTC",
          "theme": "light",
          "style": "1",
          "locale": "kr",
          "enable_publishing": false,
          "backgroundColor": "rgba(255, 255, 255, 1)",
          "gridColor": "rgba(240, 243, 250, 0)",
          "hide_top_toolbar": false,
          "hide_legend": false,
          "save_image": false,
          "container_id": "tradingview_ndx",
          "studies": [
            "RSI@tv-basicstudies",
            {"id": "MASimple@tv-basicstudies", "inputs": {"length": 200}}
          ]
          });
          </script>
        </div>
        """
        components.html(tv_widget_us, height=750)
        
        st.markdown("---")

        yf_symbols = st.session_state.sp100_state_df['Symbol'].tolist()
        # 💡 50개씩 4묶음으로 나누어 버튼 생성!
        chunks = [yf_symbols[i:i+50] for i in range(0, 200, 50)]
        labels_us = ["1위~50위", "51위~100위", "101위~150위", "151위~200위"]
        
        st.caption("야후 파이낸스 데이터 차단(Rate Limit)을 방지하기 위해 50개 종목씩 나누어 '4시간봉 EMA 200 vs 1일봉 EMA 200' 크로스 현황을 정밀 스캔합니다.")
        cols_us = st.columns(4)
        for i in range(4):
            if i < len(chunks):
                if cols_us[i].button(f"🚀 나스닥 {labels_us[i]} 스캔", use_container_width=True, key=f"btn_us_{i}"):
                    with st.spinner(f"나스닥 {labels_us[i]} 실시간 데이터 스캔 중..."):
                        time.sleep(2)
                        try:
                            data_1d_raw = yf.download(chunks[i], period="2y", interval="1d", progress=False)
                            data_1h_raw = yf.download(chunks[i], period="730d", interval="1h", progress=False)
                            
                            data_1d = data_1d_raw.get('Close', pd.DataFrame())
                            data_1h = data_1h_raw.get('Close', pd.DataFrame())
                            
                            if isinstance(data_1d, pd.Series): data_1d = data_1d.to_frame(name=chunks[i][0])
                            if isinstance(data_1h, pd.Series): data_1h = data_1h.to_frame(name=chunks[i][0])
                            
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
                                        
                                        merged = pd.merge_asof(df_4h_ma[['EMA200_4H', 'Close']], df_1d_ma[['EMA200_1D']], left_index=True, right_index=True, direction='backward').dropna()
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
                                            c_type, c_date, c_price = "최근 1년 내 없음", "-", "-"
                                
                                mask = st.session_state.sp100_state_df['Symbol'] == sym
                                st.session_state.sp100_state_df.loc[mask, '크로스 상태 (4H/1D EMA200)'] = c_type
                                st.session_state.sp100_state_df.loc[mask, '크로스 날짜'] = c_date
                                st.session_state.sp100_state_df.loc[mask, '크로스 당시 주가'] = c_price
                            
                            st.success(f"✅ 나스닥 {labels_us[i]} 스캔 완료!")
                            st.rerun() 
                        except Exception as e:
                            st.error(f"야후 파이낸스 스캔 중 오류 발생: {str(e)}")

        # 💡 히트맵용 순수 숫자 데이터 컬럼(시가총액_num, 1일_변동_num)은 화면 테이블에서 보이지 않도록 필터링!
        display_cols_us = [
            '순위', 'Symbol', '시총', 'Name', '분야 순위', '현재주가', 'RSI', 
            '1일 변동', '7일 변동', '30일 변동', '60일 변동', '120일 변동', '200일 변동', 
            '산업군(Industry)', '크로스 상태 (4H/1D EMA200)', '크로스 날짜', '크로스 당시 주가'
        ]
        
        st.dataframe(
            st.session_state.sp100_state_df[display_cols_us].style.map(color_pct, subset=['1일 변동', '7일 변동', '30일 변동', '60일 변동', '120일 변동', '200일 변동']),
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
                "크로스 당시 주가": st.column_config.TextColumn("크로스가", width="small")
            },
            use_container_width=True, 
            hide_index=True, 
            height=1100
        )
