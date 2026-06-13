import streamlit as st
import pandas as pd
import requests
import json
import uuid
import re
import io
import time
import ccxt
from datetime import datetime
from PIL import Image
import google.generativeai as genai
from theory_data import get_base_theory_dict

URL = st.secrets.get("SUPABASE_URL", "")
KEY = st.secrets.get("SUPABASE_KEY", "")
HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# --- Database Functions ---
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

def load_sector_data():
    res = requests.get(f"{URL}/rest/v1/sector_analysis?select=*&order=created_at.desc", headers=HEADERS)
    if res.status_code == 200 and res.json():
        return pd.DataFrame(res.json())
    return pd.DataFrame(columns=["id", "ticker", "sector", "market_cap", "vol_1d", "vol_1w", "vol_1m", "vol_1q", "vol_1y", "issue", "detail_data", "ai_analysis"])

def load_theory_db():
    db_dict = get_base_theory_dict()
    res = requests.get(f"{URL}/rest/v1/theory_db?select=*", headers=HEADERS)
    if res.status_code == 200 and res.json():
        for row in res.json():
            cat, title = row['category'], row['title']
            if cat not in db_dict: db_dict[cat] = {}
            db_dict[cat][title] = {
                "id": row.get('id'), 
                "content": row.get('content', ''), 
                "images": row.get('image_paths', '').split('|') if row.get('image_paths') else []
            }
    return db_dict

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
        except: pass
    return context

# --- AI Functions ---
def get_gemini_keys():
    keys = []
    if "GEMINI_API_KEY" in st.secrets: keys.append(st.secrets["GEMINI_API_KEY"])
    for k in st.secrets:
        if k.startswith("GEMINI_API_KEY_") and st.secrets[k]:
            keys.append(st.secrets[k])
    return list(set(keys))

def parse_ai_json(text):
    if not isinstance(text, str): text = str(text) if text is not None else ""
    try:
        clean_text = text.strip()
        if "```json" in clean_text: clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_text: clean_text = clean_text.split("```")[1].split("```")[0].strip()
        if clean_text.startswith("{") and clean_text.endswith("}"): return json.loads(clean_text)
        else: raise Exception("Not a JSON")
    except:
        return {"trend": "-", "key_level": "-", "momentum": "-", "volume": "-", "s_score": 0, "macro_news": "-", "analysis": text}

def ask_gemini_dynamic(prompt, imgs):
    keys = get_gemini_keys()
    if not keys: return "Gemini API 키가 설정되지 않았습니다."
    if not isinstance(imgs, list): imgs = [imgs]
    payload = [prompt] + imgs
    
    last_error = ""
    for key in keys:
        genai.configure(api_key=key)
        try:
            available_models = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            flash_models = [m for m in available_models if '1.5-flash' in m.lower()]
            pro_models = [m for m in available_models if '1.5-pro' in m.lower()]
            if not flash_models: flash_models = [m for m in available_models if 'flash' in m.lower()]
            if not pro_models: pro_models = [m for m in available_models if 'pro' in m.lower()]
            models_to_try = flash_models + pro_models
            if not models_to_try: models_to_try = available_models
            
            for model_name in models_to_try:
                try:
                    model = genai.GenerativeModel(model_name)
                    return model.generate_content(payload).text
                except Exception as e:
                    last_error = str(e)
                    if "429" in last_error or "quota" in last_error.lower(): break 
                    elif "404" in last_error or "not found" in last_error.lower(): continue 
                    else: break 
        except Exception as e:
            last_error = str(e)
            continue
    return f"모든 API 키 한도 소진 또는 오류 발생.\n에러: {last_error}"

def get_real_ocr_text(image_url):
    try:
        res = requests.get(image_url)
        img = Image.open(io.BytesIO(res.content))
        prompt = """
        이 이미지에서 '차트 캔들 옆에 있는 가격 숫자', '시간 축 숫자', '차트 내 라벨'은 완벽하게 무시해. 
        오직 차트 위/아래에 작성된 **블로그 본문 설명글, 문장 형태의 텍스트**만 정확하게 추출해. 줄바꿈 유지할 것.
        """
        return ask_gemini_dynamic(prompt, img) 
    except Exception as e: return f"이미지 다운로드 실패: {e}"

def get_real_ai_advice(image_url, ticker, reference_text=""):
    try:
        res = requests.get(image_url)
        img = Image.open(io.BytesIO(res.content))
        prompt = f"""
        이 차트 이미지를 바탕으로 **[{ticker}]** 종목에 대한 전문적인 기술적 분석을 수행해.
        반드시 아래의 JSON 데이터 형식으로만 답변해. 다른 설명이나 마크다운은 절대 넣지 마. 오직 중괄호 {{ }} 만 출력해.
        {{
          "trend": "단기 상승 / 하락 / 횡보 등 10자 이내 요약",
          "key_level": "핵심 지지/저항 가격 15자 이내 요약",
          "momentum": "RSI/MACD 등 모멘텀 상태 15자 이내 요약",
          "volume": "돌파 시 거래량 등 상태 10자 이내 요약",
          "s_score": "0에서 4 사이의 정수 숫자 (유동성 스윕, 오더블록, 패턴, 지지저항 중첩 개수 점수)",
          "macro_news": "차트상 급등/급락이 관찰될 경우, 연관 매크로 이슈나 뉴스(나스닥 커플링 등) 추론 요약. 특이사항 없으면 '특이 동향 없음'.",
          "analysis": "1) 종목/타임프레임 명시. 2) 차트 분석 조언 3~4줄 핵심 요약."
        }}
        """
        if reference_text:
            prompt += f"\n\n**[원작자 관점 동기화]**\n아래 원작자 본문 내용의 방향성(롱/숏, 지지/저항 등)을 적극 반영해줘.\n```\n{reference_text}\n```"
        return ask_gemini_dynamic(prompt, img) 
    except Exception as e: return f"이미지 다운로드 실패: {e}"

def render_ai_advice_block(title, ai_text):
    ai_data = parse_ai_json(ai_text)
    st.markdown(f"#### {title}")
    
    macro_news = ai_data.get('macro_news', '')
    if macro_news and macro_news not in ["-", "특이 동향 없음", "없음"]:
        st.error(f"🚨 **[급변동/이슈 감지]** {macro_news}")
        
    m1, m2 = st.columns(2)
    m1.metric("📈 추세 (Trend)", ai_data.get('trend', '-'))
    m2.metric("🎯 중요 레벨", ai_data.get('key_level', '-'))
    m3, m4 = st.columns(2)
    m3.metric("⚡ 모멘텀", ai_data.get('momentum', '-'))
    m4.metric("📊 거래량", ai_data.get('volume', '-'))
    
    score = ai_data.get('s_score', 0)
    try: score_val = max(0, min(4, int(score)))
    except: score_val = 0
    st.markdown(f"**🔥 S급 셋업 판독 점수: {score_val} / 4**")
    st.progress(score_val / 4.0)
    st.success(ai_data.get('analysis', ''))

def render_blog_image_html(url): return f'<div style="width: 100%; display: flex; justify-content: center; margin-bottom: 5px;"><img src="{url}" style="max-width: 100%; max-height: 70vh; width: auto; height: auto; object-fit: contain; border: 1px solid #ddd; padding: 2px;" /></div>'
def render_crisp_image_html(url): return f'<div style="width: 100%; display: flex; justify-content: flex-start; margin-bottom: 10px;"><img src="{url}" style="max-width: 100%; max-height: 80vh; width: auto; height: auto; object-fit: contain; image-rendering: crisp-edges; border: 2px solid #4a90e2; padding: 2px; box-shadow: 2px 2px 8px rgba(0,0,0,0.1);" /></div>'

def get_file_group_info(filename):
    name_without_ext = os.path.splitext(filename)[0]
    matches = re.findall(r'(\d+)(?:-(\d+))?', name_without_ext)
    if matches:
        return matches[-1][0], int(matches[-1][1] if matches[-1][1] else '0')
    return str(uuid.uuid4().hex[:4]), 0

# --- 생존 매매 봇 기능 추가 ---
def execute_survival_trade(api_key, secret_key, passphrase, symbol, side, sl_percent, reason, risk_limit_percent):
    try:
        exchange = ccxt.bitget({
            'apiKey': api_key,
            'secret': secret_key,
            'password': passphrase,
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'} 
        })
        
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        balance = exchange.fetch_balance()
        total_usdt = balance['USDT']['free']
        
        max_loss_usdt = total_usdt * (risk_limit_percent / 100.0)
        loss_per_coin = current_price * (sl_percent / 100.0)
        amount = round(max_loss_usdt / loss_per_coin, 3) 
        
        if amount <= 0:
            return False, f"❌ 진입 가능 수량이 0입니다. (잔고: {round(total_usdt, 2)} USDT)"

        stop_loss_price = current_price * (1 - sl_percent/100.0) if side == 'buy' else current_price * (1 + sl_percent/100.0)

        entry_order = exchange.create_order(symbol, 'market', side, amount)

        sl_side = 'sell' if side == 'buy' else 'buy'
        sl_params = {
            'stopPrice': stop_loss_price,
            'triggerPrice': stop_loss_price,
            'reduceOnly': True
        }
        sl_order = exchange.create_order(symbol, 'market', sl_side, amount, params=sl_params)

        insert_data = {
            "date": datetime.today().strftime("%Y-%m-%d"),
            "ticker": symbol.split('/')[0],
            "timeframe": "Auto",
            "setup_pattern": "생존매매 (자동SL)",
            "position": "Long" if side == 'buy' else "Short",
            "result": "진입완료",
            "rr_ratio": "-",
            "profit": 0,
            "entry_basis": reason,
            "exit_basis": f"자동 스탑로스 설정 완료: {stop_loss_price}"
        }
        insert_db("trade_history", insert_data)

        return True, f"✅ 진입 성공! (평단가: {current_price} | 수량: {amount} | 스탑로스: {stop_loss_price})"
    except Exception as e:
        return False, f"❌ 실행 오류 발생: {str(e)}"
