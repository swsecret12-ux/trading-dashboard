import streamlit as st
import pandas as pd
import requests
import json
import uuid
import re
import os
import io
import time
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
# --- 3. 데이터 로드 함수 (목차 템플릿 + 학습 내용 포함) ---
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
    # 💡 1. 유동성 스윕
    liquidity_text = """**■ 1. 유동성(Liquidity)의 기본 개념**
* **트레이딩에서의 유동성:** 대기 중인 미체결 주문, 특히 개미들의 **'손절 물량(Stop Loss)'**이 뭉쳐있는 구간.
* **스마트 머니(세력)의 목표:** 세력이 대량 매수를 하려면 누군가 대량으로 팔아주어야 함. 따라서 개미들의 손절 물량이 쏟아지는 곳으로 가격을 밀어 유동성을 흡수(매집)한 뒤 방향을 틈. (유동성은 차트를 움직이는 연료!)

**■ 2. 유동성 구간 찾기 & 작도법**
* **위치:** 99%의 트레이더들이 손절을 거는 직전 **전고점(Swing High)과 전저점(Swing Low)**.
* **작도:** 트레이딩뷰 **'자석 모드(Magnet)'**를 켜고 전고/전저점 캔들 꼬리 끝에 Shift 키를 누른 채 정확한 수평선을 작도.

**■ 3. 🎯 진입 트리거 (핵심)**
* 가격이 선을 돌파한 후, 반드시 **'봉 마감'**을 지켜보아야 함. (미리 예측 진입 금지)
* 꼬리(Wick)만 길게 남기고 캔들의 몸통(Body)이 선 안쪽으로 다시 올라와서 마감했을 때(스윕 확인) 즉시 진입.
* *(주의: 캔들 몸통 자체가 유동성 선 밖에서 마감해버리면 추세가 강하게 밀리는 것이므로 진입 포기)*

**■ 4. 리스크 관리 (SL / TP)**
* **손절(SL):** 유동성을 찌르고 돌아온 캔들의 **'꼬리 끝점'**. (매우 직관적이고 짧은 손절 라인)
* **익절(TP):** 반대편에 있는 다음 주요 유동성 구간 (다음 전고점 또는 전저점)."""

    # 💡 2. 추세선과 채널
    channel_text = """**■ 1. 추세선/채널의 진짜 의미 (세력의 관점)**
* **일반적인 함정:** 초보자들은 채널을 '가격이 지켜주는 든든한 방벽'으로 맹신함.
* **세력의 의도:** 세력은 개미들을 채널 안에 가두어 심리적 안정감을 준 뒤, 채널 상/하단에 매수/매도(손절) 주문이 잔뜩 쌓이기를 기다림. (기울어진 유동성)
* **사냥의 순간 (Fake Out):** 세력은 고의로 채널을 깨부수어(이탈시켜) 개미들의 손절 물량과 돌파 매매 물량을 한 번에 흡수(매집)한 후 원래 방향으로 강하게 되돌림.

**■ 2. 🎯 매매 셋업 A: 채널 이탈 (Fake Out 역이용)**
* **조건:** 캔들이 뚜렷한 채널의 상/하단을 강하게 돌파(이탈)함.
* **진입 트리거 (핵심):** 돌파했던 캔들이 다음 캔들(또는 꼬리를 달고) **다시 채널 내부로 들어와서 '봉 마감'**을 할 때 진입. (세력의 유동성 사냥이 끝났다는 강력한 신호)
* **손절(SL):** 채널을 이탈하며 찌른 **'가장 깊은 꼬리의 끝점'** (매우 타이트하고 객관적인 손절).

**■ 3. 🎯 매매 셋업 B: 채널 유지 (리테스트 방어)**
* **조건:** 캔들이 채널 선에 닿았을 때.
* **진입 트리거:** 채널 선을 뚫고 나갔던 캔들이, 몸통은 선 안쪽에 두고 **'꼬리만 채널 선을 찌르고 마감'** 했을 때 진입.
* **손절(SL):** 그 꼬리의 끝점.

**■ 4. 💰 무적의 리스크 관리 (반익반본)**
* **1차 익절:** 진입 후 목표한 수익 구간(예: 채널의 반대편, 또는 손익비 1:2 지점 등)에 도달하면 **반드시 물량의 1/2(절반)을 익절**하여 수익을 챙김.
* **본절 로스 (핵심):** 절반 익절과 동시에, 나머지 절반 물량의 손절(SL) 라인을 **나의 '진입 평단가'**로 끌어올림.
* **결과:** 이후 차트가 내 예상대로 흘러가면 추가 수익 극대화, 만약 갑자기 추세가 꺾 폭락하더라도 나머지 물량은 본전에서 컷트되므로 **절대 잃지 않는 무적의 포지션** 완성."""

    # 💡 3. 오더블록
    orderblock_text = """**■ 1. 오더블록(Order Block)이란?**
* 세력(스마트 머니)이 시장을 장악하고 추세를 반전시키기 전에 만들어지는 **'세력의 발자국'**입니다. 이 구간에는 엄청난 주문이 뭉쳐있거나, 세력의 미체결 주문이 남아있을 가능성이 매우 높습니다.
* 단, 모든 오더블록이 의미가 있는 것은 아닙니다. 반드시 **'유동성 스윕'과 연계**해서 생각해야 강력한 무기가 됩니다.

**■ 2. 오더블록의 성립 조건 (진짜 오더블록 찾기)**
오더블록이라고 해서 무조건 선을 긋는 것이 아닙니다. 다음 세 가지 조건을 만족해야 **'가치가 있는(진짜) 오더블록'**으로 취급합니다.
1.  **유동성 스윕:** 이전에 쌓여있던 유동성(전고점/전저점 등)을 사냥(스윕)하는 움직임이 선행되어야 합니다.
2.  **강력한 추세 돌파:** 유동성을 흡수한 뒤, 시장의 구조를 깨버리는(BOS/CHOCH) 강력한 반전 캔들이 나타나야 합니다.
3.  **갭(FVG) 발생:** 반전하는 캔들에 의해 불균형한 공간인 **FVG(Fair Value Gap)**가 함께 발생해야 신뢰도가 높아집니다.

**■ 3. 오더블록 작도 방법 (캔들 감싸기)**
* **상승 오더블록 (Bullish OB):** 롱(매수) 진입을 노릴 때 찾습니다.
    * 추세를 상승으로 반전시킨 강력한 상승 캔들(양봉)의 **'직전에 나타난 하락 캔들(음봉)'**을 찾습니다.
    * 이 음봉의 **꼬리 끝부터 몸통 끝까지**를 사각형 박스로 감싸 그립니다.
* **하락 오더블록 (Bearish OB):** 숏(매도) 진입을 노릴 때 찾습니다.
    * 추세를 하락으로 반전시킨 강력한 하락 캔들(음봉)의 **'직전에 나타난 상승 캔들(양봉)'**을 찾습니다.
    * 이 양봉의 **꼬리 끝부터 몸통 끝까지**를 사각형 박스로 감싸 그립니다.
    *(팁: 캔들의 몸통이 비정상적으로 길거나 꼬리가 비정상적으로 길다면, 상황에 맞춰 몸통만 감싸거나 꼬리만 감싸는 식으로 융통성을 발휘하기도 합니다. 본인의 눈에 가장 예쁘고 깔끔하게 보이는 선을 긋는 것이 중요합니다.)*

**■ 4. 🎯 오더블록 실전 매매 전략 (리테스트 진입)**
* **진입 트리거 (리테스트):** 가격이 멀리 도망갔다가 다시 돌아와서 **오더블록 박스를 '터치(Test)'**할 때를 노립니다.
    * (공격적) 박스 상단에 닿자마자 바로 진입
    * (안정적) 가격이 박스 근처에 왔을 때, 하위 타임프레임으로 내려가서 한 번 더 작은 타임프레임의 반전(스윕+오더블록)을 확인하고 진입
* **손절 (SL):** 매우 직관적이고 칼같은 손절이 가능합니다. **오더블록 박스의 반대쪽 끝(꼬리 끝)**을 이탈하여 '봉 마감'이 될 때가 완벽한 손절 라인입니다. 이 선이 깨지면 세력의 방어선이 뚫린 것이므로 미련 없이 도망쳐야 합니다.
* **익절 (TP):** 오더블록 매매는 손익비가 매우 훌륭합니다.
    * **1차 익절:** 직전의 의미 있는 전고점/전저점 (가장 가까운 유동성 구간)
    * 1차 익절 후 역시 **'반익반본(절반 익절 후 본절 로스)'** 전략을 통해 리스크를 완벽하게 제거하고 홀딩합니다."""

    # 💡 4. FVG
    fvg_text = """**■ 1. FVG(Fair Value Gap)란?**
* **의미:** 스마트 머니(세력)가 대규모 물량을 한 번에 시장가로 긁어버리면서 발생하는 **'공정 가치의 틈(불균형 공간)'**입니다. 매수자와 매도자의 균형이 깨지며 캔들 사이에 빈 공간이 생깁니다.
* **중요성:** FVG는 단순한 캔들의 틈이 아닙니다. **"세력이 급하게 가격을 움직이면서 남긴 흔적"**이자, 나중에 가격이 다시 자석처럼 돌아와 이 공간을 채우고 반전할 가능성이 매우 높은 핵심 지지/저항(S/R) 역할을 합니다.

**■ 2. FVG의 형태와 조건**
FVG는 항상 **'3개의 캔들'** 조합에서 발견됩니다.

1.  **상승형 FVG (Bullish FVG):**
    * 형태: 연속된 상승 캔들.
    * 작도: **첫 번째 캔들의 고점**과 **세 번째 캔들의 저점** 사이에 빈 공간이 있을 때, 그 사이 공간이 FVG입니다.
2.  **하락형 FVG (Bearish FVG):**
    * 형태: 연속된 하락 캔들.
    * 작도: **첫 번째 캔들의 저점**과 **세 번째 캔들의 고점** 사이에 빈 공간이 있을 때, 그 사이 공간이 FVG입니다.

**■ 3. FVG의 핵심 개념: "채우려는 성질"과 "S/R Flip"**
* **메워짐:** FVG는 가격의 불균형 상태이므로, 가격은 다시 그 자리로 돌아와 빈 공간을 채우려는 성질이 있습니다.
* **S/R Flip (지지/저항 반전):**
    * **기본:** FVG는 닿으면 반전하는 지지/저항선 역할을 합니다.
    * **반전:** 만약 캔들이 이 FVG 영역을 완전히 돌파(봉 마감)해버린다면? 그 FVG는 소멸되는 것이 아닙니다!
    * **Inverse FVG:** 돌파된 FVG는 성질이 반대로 바뀝니다. (지지가 저항으로, 저항이 지지로) 이를 **S/R Flip(지지 저항 반전)**이라고 부르며, 이후 이 돌파된 FVG를 리테스트할 때 매우 좋은 진입 타점이 됩니다.

**■ 4. 🎯 FVG 실전 활용 및 타점**
* **신뢰도:** FVG 단독으로 쓰기보다는, **오더블록(Order Block)이나 주요 구조물과 겹쳐서(Confluence)** 발생했을 때 신뢰도가 기하급수적으로 올라갑니다.
* **진입 전략:**
    * 가격이 되돌림을 주어 FVG 영역 안으로 들어오면, 하위 타임프레임에서 반전 시그널(스윕 등)을 확인하고 진입합니다.
* **Inverse FVG 전략:**
    * 돌파된 FVG(Inverse FVG)를 활용할 때, 그 FVG 영역이 강력한 지지/저항선이 되므로 돌파 후 리테스트 시에 진입합니다."""

    # 💡 5. 차트 패턴의 개요
    chart_pattern_intro_text = """**■ 1. 차트 패턴의 본질: 단순한 '모양'이 아니다!**
* **흔한 오해:** 많은 초보자들이 차트 패턴을 단순히 과거에 나타났던 '모양'으로만 암기하려고 합니다. (예: "W 모양이니까 오르겠지", "M 모양이니까 내리겠지")
* **진짜 의미:** 차트 패턴은 그 모양 자체가 마법을 부리는 것이 아닙니다. **"사람들의 심리(공포, 탐욕, 희망, 절망)가 매수와 매도라는 행동으로 캔들에 찍히고, 그 캔들들이 모여서 특정한 모양(패턴)을 만들어낸 결과물"**입니다. 즉, 패턴은 **'시장 참여자들의 집단 심리가 담긴 설계도'**입니다.

**■ 2. 패턴의 존재 이유: '심리'를 읽어라**
* 왜 패턴이 생기는 걸까요? 그 패턴이 형성되는 과정에서 **특정한 방향으로 시장 참여자들의 심리가 쏠리기 때문**입니다.
* 패턴의 모양(W, M 등)만 외우는 것은 껍데기만 외우는 것과 같습니다. 그 패턴이 왜 그런 모양으로 생겼는지, 그 안에서 매수자와 매도자가 어떤 힘겨루기를 하고 있는지를 이해해야 패턴이 완성되었을 때 강력한 타점을 잡을 수 있습니다.

**■ 3. 앞으로 다룰 핵심 패턴들**
차트에는 수많은 패턴이 있지만, 실전에서 가장 빈번하게 나타나고 승률이 높은 핵심 패턴들을 깊이 있게 다룰 예정입니다.
1.  **더블 탑/더블 바텀 (Double Top/Bottom)**
2.  **헤드 앤 숄더 / 역 헤드 앤 숄더 (Head & Shoulders / Inverse H&S)**
3.  **컵 앤 핸들 (Cup and Handle)**
4.  **다이아몬드 패턴 (Diamond Pattern)**
5.  **아담 앤 이브 패턴 (Adam and Eve)**
* 이 패턴들을 단순히 '모양 찾기'가 아니라, 세력의 유동성 사냥과 개미들의 심리 상태를 바탕으로 완벽하게 해부해 보겠습니다."""

    # 💡 6. 컵 앤 핸들
    cup_and_handle_text = """**■ 1. 컵 앤 핸들 (Cup & Handle)의 본질**
* **의미:** 1988년 전설적인 투자자 윌리엄 오닐이 소개한 패턴. 세력이 장기간에 걸쳐 물량을 조용히 매집하고, 마지막으로 개미들의 물량(본전 심리)을 털어낸 뒤 강하게 상승하는 전형적인 **상승 지속 패턴**입니다.
* **모양:** 이름 그대로 커피잔(Cup)과 손잡이(Handle)가 결합된 형태를 띱니다.

**■ 2. 패턴 형성의 심리 과정 (왜 이런 모양이 나올까?)**
* **컵(Cup) 형성:** * 고점에서 물린 개미들의 실망 매물이 나오며 가격이 천천히 하락합니다. (U자형 바닥)
    * 바닥 구간에서 세력은 가격을 올리지 않고 조용히, 그리고 길게 물량을 매집합니다. 이때 거래량은 바짝 마릅니다.
    * 매집이 끝나면 세력은 가격을 서서히 올려 이전 고점(컵의 입구) 근처까지 도달합니다.
* **핸들(Handle) 형성:**
    * 가격이 전고점에 다다르면, 바닥에서 버티던 개미들의 **'본전 심리'**가 발동하여 엄청난 매도 물량이 쏟아집니다.
    * 세력은 이 물량을 다 받아먹으면서 가격이 살짝 눌리게 만드는데, 이것이 손잡이(핸들) 모양이 됩니다.
    * 악성 매물이 모두 소화되고 나면, 세력은 강한 거래량과 함께 저항선을 돌파하며 폭등시킵니다.

**■ 3. 컵 앤 핸들의 3가지 핵심 조건**
아무 둥근 모양이나 컵 앤 핸들이 아닙니다! 다음 조건을 충족해야 신뢰도가 높습니다.
1. **형태:** 컵의 바닥은 V자가 아니라 **둥근 U자형**이어야 합니다. (충분한 매집 시간이 필요함)
2. **비율:** 핸들의 깊이(눌림)는 컵 전체 높이의 절반(50%)을 넘지 않는 것이 좋습니다. **이상적인 눌림 폭은 30% 내외**입니다. (핸들이 너무 깊으면 추세가 꺾인 것으로 봅니다.)
3. **거래량 (가장 중요!):**
    * 컵의 왼쪽 하락장에서는 거래량이 줄어들고, 둥근 바닥에서는 거래량이 씨가 마릅니다.
    * 컵의 오른쪽 상승장에서는 다시 거래량이 점차 증가해야 합니다.
    * **핸들 구간(눌림목)에서는 반드시 거래량이 줄어들어야 합니다.** (매도세가 말라가고 있다는 증거)
    * **마지막 저항선을 돌파할 때는 폭발적인 거래량이 터져야 합니다.**

**■ 4. 🎯 실전 매매 타점**
* **진입 (Entry):** 핸들 형성을 마치고 **'컵의 입구 저항선(Neckline)'을 돌파할 때** 진입합니다. (돌파 후 리테스트 때 진입하면 더욱 안전합니다.)
* **손절 (SL):** 핸들의 최하단 저점. (이곳이 깨지면 매물 소화 실패로 간주합니다.)
* **익절 (TP):** 최소 목표가는 돌파된 넥라인에서부터 **'컵의 바닥까지의 깊이'**만큼 위로 올린 1:1 지점입니다."""

    # 💡 7. 다이아몬드 패턴
    diamond_pattern_text = """**■ 1. 다이아몬드 패턴의 본질**
* **의미:** 차트에서 매우 드물게 나타나지만, 한 번 출현하면 **추세의 전환(반전)**을 알리는 아주 강력한 신호입니다. 
* **형태:** 이름 그대로 마름모(다이아몬드) 모양을 띠며, 두 가지 상반된 패턴이 결합된 형태입니다.
    1. **전반부 (확산형 패턴):** 고점은 높아지고 저점은 낮아지며 가격의 변동폭이 갈수록 커집니다. (매수/매도 세력의 치열한 싸움으로 휩소(가짜 돌파)가 많이 발생)
    2. **후반부 (수렴형 패턴 - 삼각수렴):** 양쪽 세력의 힘이 서서히 빠지면서 고점은 낮아지고 저점은 높아지며 변동폭이 점점 작아집니다. (승자가 결정되기 직전의 숨 고르기)

**■ 2. 발생 위치에 따른 분류 (Top vs Bottom)**
다이아몬드 패턴은 '어디서(추세의 끝자락)' 출현했느냐가 가장 중요합니다.
* **다이아몬드 탑 (Diamond Top):**
    * **위치:** 긴 상승 추세의 끝(고점)에서 발생.
    * **심리:** 매수세가 힘을 다하고 매도세가 등장하여 치열하게 싸우다가, 결국 매도세가 승리하며 **강력한 하락 반전**을 예고합니다.
* **다이아몬드 바텀 (Diamond Bottom):**
    * **위치:** 긴 하락 추세의 끝(저점)에서 발생.
    * **심리:** 투매가 쏟아진 후 저가 매수세가 유입되어 싸우다가, 결국 매수세가 승리하며 **강력한 상승 반전**을 예고합니다.

**■ 3. 작도 방법 및 거래량 힌트**
* **작도:** 확산하는 구간의 고점/저점 추세선 2개 + 수렴하는 구간의 고점/저점 추세선 2개, 총 4개의 선을 그어 마름모 모양을 만듭니다.
* **거래량 힌트 (중요):**
    * 전반부(확산형)에서는 매수/매도가 치열하게 싸우므로 **거래량이 높게 유지되거나 튀는 현상**이 발생합니다.
    * 후반부(수렴형)로 갈수록 점차 **거래량이 줄어들며 마릅니다.**
    * 마지막 경계선을 **돌파/이탈할 때 거래량이 크게 터져야** 찐 반전 신호로 간주합니다.

**■ 4. 🎯 실전 매매 타점**
* **진입 (Entry):** 다이아몬드의 후반부 수렴 지점을 **이탈/돌파하며 봉 마감**할 때 진입합니다. (안전하게는 리테스트를 확인하고 들어갑니다.)
    * 다이아몬드 탑: 하단 추세선을 하향 이탈할 때 숏(매도) 진입.
    * 다이아몬드 바텀: 상단 추세선을 상향 돌파할 때 롱(매수) 진입.
* **손절 (SL):** 돌파/이탈한 방향의 **반대편 추세선 안으로 가격이 다시 들어와서 봉 마감**하면 손절합니다. (가짜 돌파 방어)
* **익절 (TP):** 최소 목표가는 **'다이아몬드 패턴의 가장 넓은 세로폭(최고점과 최저점의 차이)'**만큼 돌파한 방향으로 1:1 대칭하여 설정합니다."""

    # 💡 8. 아담 앤 이브 패턴
    adam_eve_text = """**■ 1. 아담 앤 이브 (Adam & Eve) 패턴의 본질**
* **의미:** 쌍바닥(Double Bottom) 또는 쌍봉(Double Top)의 변형된 형태로, **'날카로운 골짜기(Adam)'**와 **'둥근 골짜기(Eve)'**가 결합된 강력한 추세 반전 패턴입니다.
* **핵심:** 두 번의 바닥(또는 고점)을 찍지만, 그 두 번의 형태와 심리가 완전히 다르다는 것이 핵심입니다.

**■ 2. 패턴의 형태와 심리 (왜 이런 모양이 나올까?)**
* **아담 (Adam - V자형 바닥):**
    * **형태:** 폭포수처럼 쏟아지다가 급반등하는 **날카로운 V자 모양**입니다.
    * **심리:** 시장의 극도의 공포와 패닉 셀(투매)이 나오며, 이를 세력이 급하게 밑에서 다 받아먹으면서 V자 반등이 나옵니다. 이때 **거래량이 크게 터집니다.**
* **이브 (Eve - U자형 바닥):**
    * **형태:** 아담 이후 다시 하락하지만, 이전처럼 날카롭지 않고 **넓고 완만한 U자 모양(접시 모양)**을 만듭니다.
    * **심리:** 아담에서 털리지 않은 개미들을 서서히 지치게 만들며, 세력이 긴 시간에 걸쳐 조용히 물량을 매집(축적)하는 구간입니다. 매도세가 말라가므로 **거래량이 눈에 띄게 줄어듭니다.**

**■ 3. 아담 앤 이브의 핵심 확인 조건**
1. **순서:** 반드시 V자(아담)가 먼저 나오고, 그 다음에 U자(이브)가 나와야 신뢰도가 높습니다. (패닉 후 안정화의 자연스러운 수순)
2. **깊이:** 이브(U자)의 저점은 아담(V자)의 저점과 비슷하거나 살짝 높은 것이 이상적입니다.
3. **거래량 변화 (필수 체크):** 아담 구간에서는 거래량이 폭발하고, 이브 구간의 바닥에서는 거래량이 바짝 말라야 하며, 마지막 넥라인 돌파 시 다시 거래량이 크게 터져야 합니다.

**■ 4. 🎯 실전 매매 타점**
* **진입 (Entry):** 아담과 이브 사이에 만들어진 **'중앙 고점(넥라인, Neckline)'을 돌파할 때** 진입합니다. (돌파 후 지지로 바뀌는 리테스트를 확인하고 진입하는 것이 휩소를 피하는 가장 안전한 방법입니다.)
* **손절 (SL):** 넥라인 돌파 캔들의 저점 또는 이브(Eve)의 최하단 저점 이탈 시 손절합니다.
* **익절 (TP):** 최소 목표가는 넥라인에서부터 **'아담(V자)의 바닥까지의 깊이'**만큼 위로 1:1 대칭하여 설정합니다."""

    # 💡 9. 거짓 돌파 및 트랩 (Fake out & Trap)
    fakeout_trap_text = """**■ 1. 거짓 돌파(Fake out)와 함정(Trap)의 본질**
* 둘 다 돌파하는 척하다가 다시 원래 구조물(박스권 등) 안으로 들어오는 **'세력의 유동성 사냥(개미털기)'** 현상입니다. 
* 세력은 개미들의 '추격 매수(돌파 매매)' 물량과 반대 포지션의 '손절' 물량을 잡아먹고 반대 방향으로 강하게 시세를 움직입니다.

**■ 2. Fake out (휩소) vs Trap (함정)의 결정적 차이**
가장 중요한 핵심은 돌파 실패 후, 다시 원래 구조물 안으로 들어와서 **'어떤 바닥(또는 고점)'**을 만드느냐에 있습니다.

* **Fake out (휩소):**
    * **특징:** 돌파 실패 후 구조물 안으로 들어와서 **'단 하나의 뾰족한 바닥(V자 반등)'**만 만들고 그대로 반대편으로 직행합니다.
    * **단점:** V자로 급하게 올라가 버리기 때문에, 눈으로 확인하고 따라붙기(진입하기)가 매우 어렵습니다.

* **Trap (함정):**
    * **특징:** 돌파 실패 후 구조물 안으로 들어와서 **'두 개 이상의 바닥(쌍바닥 이상)'**을 만듭니다. 
    * **심리:** 첫 번째 바닥 후 살짝 반등을 주어 '데드캣 바운스'를 노리는 숏(매도) 투자자들을 꼬십니다. 그리고 두 번째 바닥을 만들면서 이 숏 투자자들의 물량까지 한 번 더 완벽하게 흡수(매집)합니다.
    * **장점 (핵심):** 쌍바닥을 만들며 시간을 끌어주기 때문에, 우리가 차트를 분석하고 **'여유롭게 진입 타점'을 잡을 수 있는 최고의 기회**가 됩니다.

**■ 3. 🎯 실전 매매 셋업 (Trap을 노려라!)**
Fake out은 따라잡기 힘들지만, Trap은 완벽한 진입 찬스를 제공합니다.

* **진입 트리거 (Trap 매매):**
    1. 하향 돌파 실패 후 다시 박스권으로 들어왔다. (세력의 유동성 사냥 의심)
    2. 첫 번째 바닥을 찍고 반등 후, **두 번째 바닥을 만들 때(쌍바닥 지지 확인 시)** 진입합니다. 
    3. *이때 두 번째 바닥이 첫 번째 바닥보다 살짝 높은 짝궁뎅이 쌍바닥이면 신뢰도가 더욱 높습니다.*
* **손절 (SL):** * 두 번째 바닥을 지지하지 못하고, **첫 번째 바닥(가장 깊었던 꼬리 끝)을 다시 이탈하여 봉 마감할 때** 칼같이 손절합니다. (이 선이 뚫리면 세력의 방어선이 깨진 진짜 하락 추세입니다.)
* **익절 (TP):** * 세력이 유동성을 충분히 모았으므로, 최소한 **박스권(구조물)의 상단(반대편 끝)**까지는 무난하게 도달할 확률이 높습니다. 이를 1차 익절(반익반본) 목표로 삼습니다."""

    # 💡 10. 실전 매매 1 (탑다운 분석)
    top_down_text = """**■ 1. 핵심 철학: "숲을 보고, 나무를 봐라"**
* **초보자들의 흔한 실수:** 5분봉 등 작은 시간대(나무)만 보고 당장 눈앞에 나타난 패턴이나 상승/하락 신호에 급하게 매매를 진입합니다. 이는 마치 숲 전체가 불타고 있는데, 내 앞의 나무 한 그루가 멀쩡해 보인다고 그곳에 집을 짓는 것과 같습니다.
* **탑다운 분석 (Top-Down Analysis):** 반드시 가장 큰 시간대(일봉, 4시간봉 등)에서 전체적인 시장의 방향과 큼직한 구조물을 파악한 뒤, 점차 작은 시간대로 내려오며 정밀한 진입 타점을 잡는 방법입니다.

**■ 2. 멀티 타임프레임 (Multi-Timeframe) 분석 단계**
트레이딩의 승률을 기하급수적으로 높이는 3단계 분석법입니다.

* **[1단계] 상위 타임프레임 (일봉 1D / 주봉 1W) - "숲의 방향과 경계선 파악"**
    * 목적: 전체적인 시장의 큰 추세(상승장인지 하락장인지)와 거대한 매물대를 파악합니다.
    * 작도: 가장 큼직하고 뚜렷한 추세선, 거대한 오더블록, 강력한 지지/저항선 등 굵직한 구조물을 그려둡니다.
* **[2단계] 중위 타임프레임 (4시간봉 4H / 1시간봉 1H) - "나무들이 모인 구역 파악"**
    * 목적: 상위 타임프레임에서 그어둔 큰 틀 안에서, 현재 가격이 어디쯤 위치해 있는지 파악합니다.
    * 작도: 현재 형성되고 있는 채널이나, 가까운 유동성(전고/전저점), 중기적인 FVG 등을 확인하여 내가 매매할 '작전 반경'을 설정합니다.
* **[3단계] 하위 타임프레임 (15분봉 15m / 5분봉 5m) - "정밀 타격(Entry) 지점 포착"**
    * 목적: 상위와 중위 타임프레임의 분석을 바탕으로, 리스크(손절)를 최소화할 수 있는 정확한 진입 타이밍을 잡습니다.
    * 액션: 큰 추세의 방향과 일치하는 쪽으로, 유동성 스윕, 작은 오더블록 터치, 패턴 돌파 등의 구체적인 셋업이 나올 때 방아쇠를 당깁니다.

**■ 3. 🎯 실전 예시 (큰 흐름에 순응하라)**
* 일봉(상위)에서 거대한 하락 추세선 아래에 가격이 짓눌려 있다면? 
    * 5분봉(하위)에서 아무리 예쁜 쌍바닥(상승 패턴)이 나오더라도 롱(매수) 진입은 굉장히 위험합니다. 이는 큰 폭포수 아래에서 작은 돌멩이 하나 밟고 서 있는 것과 같습니다.
    * 반대로, 5분봉에서 하락 패턴이나 상단 유동성을 스윕하고 내려오는 모습이 보인다면? 큰 추세(하락)와 작은 추세(하락)가 일치하므로 아주 강하게 숏(매도) 진입을 노려볼 수 있습니다."""

    # 💡 11. 실전 매매 2 (차트는 항상 깨끗하게) - 신규 업데이트
    clean_chart_text = """**■ 1. 정보의 과부하(Cognitive Overload) 경계하기**
* **초보자들의 흔한 착각:** 보조 지표(RSI, MACD, 볼린저 밴드, 이평선 등)를 많이 띄워놓고, 선을 이리저리 많이 그어두면 자신이 '전문적인 분석'을 하고 있다고 착각합니다.
* **실제 발생하는 문제:** 인간의 뇌는 한 번에 처리할 수 있는 정보의 양에 한계가 있습니다. 
    * A 지표는 매수(Long) 신호를 보내고, B 지표는 매도(Short) 신호를 보내고, C 작도 선은 지지선인데, D 작도 선은 저항선인 상황이 빈번하게 발생합니다.
    * 결국 정보가 서로 충돌하면서 **확신 있는 진입을 하지 못하고 혼란(뇌동매매)에 빠지거나, 좋은 타점을 눈앞에 두고도 놓치게 됩니다.**

**■ 2. 핵심 원칙: "필요한 것만 남기고 다 지우자"**
진짜 고수들의 차트는 놀라울 정도로 단순하고 깨끗합니다.

* **지표 다이어트:** * 수많은 보조 지표를 지우고, 가격(Price)과 거래량(Volume)이라는 가장 본질적인 데이터에만 집중하세요. (가격 자체가 모든 정보가 선반영된 궁극의 지표입니다.)
* **작도 다이어트:**
    * 과거의 모든 고점과 저점에 선을 긋지 마세요. 
    * 현재 가격의 움직임에 직접적인 영향을 미치는 **'가장 최근의, 가장 의미 있는 핵심 구조물(오더블록, FVG, 유동성 스윕 라인)'** 몇 개만 남기고 과감히 지워버려야 합니다.

**■ 3. 깨끗한 차트가 가져다주는 엄청난 장점**
* **명확한 판단력:** 노이즈(불필요한 정보)가 사라지면, 현재 시장의 진짜 구조(세력의 의도)가 한눈에 들어옵니다.
* **기계적인 매매:** 차트가 깔끔할수록 "여기에 닿으면 진입, 저기가 깨지면 손절"이라는 나만의 셋업과 시나리오가 선명해집니다.
* **멘탈 관리:** 복잡한 지표들에 휘둘리지 않으므로, 뇌동매매가 줄어들고 심리적인 안정감을 유지하며 트레이딩을 할 수 있습니다."""

    # 💡 전체 커리큘럼 뼈대 조립
    db_dict = {
        "1. 기본 이론 규칙": {
            "유동성 스윕 (Liquidity Sweep)": {"id": "default", "content": liquidity_text, "images": []},
            "추세선과 채널 (Trendline & Channel)": {"id": "default", "content": channel_text, "images": []},
            "오더블록 (Order Block)": {"id": "default", "content": orderblock_text, "images": []},
            "FVG (Fair Value Gap)": {"id": "default", "content": fvg_text, "images": []}
        },
        "2. 차트 패턴": {
            "차트 패턴의 개요": {"id": "default", "content": chart_pattern_intro_text, "images": []},
            "컵앤 핸들 패턴 (Cup & Handle)": {"id": "default", "content": cup_and_handle_text, "images": []},
            "다이아몬드 패턴 (Diamond)": {"id": "default", "content": diamond_pattern_text, "images": []},
            "아담앤 이브 패턴 (Adam & Eve)": {"id": "default", "content": adam_eve_text, "images": []}
        },
        "3. 거짓 돌파 (트랩)": {
            "거짓 돌파(Fake out)와 함정(Trap)": {"id": "default", "content": fakeout_trap_text, "images": []}
        },
        "4. 실전 매매 (멀티 타임프레임)": {
            "실전 1: 숲을 보고 나무를 봐라 (탑다운 분석)": {"id": "default", "content": top_down_text, "images": []},
            "실전 2: 차트는 항상 깨끗하게 유지하라": {"id": "default", "content": clean_chart_text, "images": []},
            "실전 3 (예정)": {"id": "default", "content": "강의 학습 후 업데이트될 예정입니다.", "images": []},
            "실전 4 (예정)": {"id": "default", "content": "강의 학습 후 업데이트될 예정입니다.", "images": []},
            "실전 5 (예정)": {"id": "default", "content": "강의 학습 후 업데이트될 예정입니다.", "images": []},
            "실전 6 (예정)": {"id": "default", "content": "강의 학습 후 업데이트될 예정입니다.", "images": []}
        },
        "5. 심화 (하모닉 패턴)": {
            "하모닉 패턴 심층 자료 (예정)": {"id": "default", "content": "강의 학습 후 업데이트될 예정입니다.", "images": []}
        }
    }

    # 클라우드 DB(Supabase)에서 영우님이 실제로 추가/수정한 데이터를 가져와서 기본 뼈대에 덮어씌웁니다.
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

# ==========================================
# --- 4. 🚀 무료 AI(Gemini) 무한 좀비 추적 시스템 ---
# ==========================================
def ask_gemini_dynamic(prompt, img):
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name.replace('models/', '')
                if '2.5' not in name and 'exp' not in name and 'thinking' not in name:
                    available_models.append(name)
        
        flash_models = [m for m in available_models if 'flash' in m.lower()]
        pro_models = [m for m in available_models if 'pro' in m.lower()]
        
        models_to_try = flash_models + pro_models
        if not models_to_try:
            models_to_try = available_models
            
        last_error = ""
        
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content([prompt, img])
                return response.text
            except Exception as e:
                last_error = str(e)
                if "429" in last_error or "quota" in last_error.lower() or "404" in last_error or "not found" in last_error.lower():
                    time.sleep(1) 
                    continue
                else:
                    break 
                
        return f"모든 모델 시도 실패. 일일 한도가 모두 소진되었거나 알 수 없는 접속 오류입니다.\n마지막 에러: {last_error}"
        
    except Exception as e:
        return f"AI 시스템 초기화 실패: {e}"

def get_real_ocr_text(image_url):
    if "GEMINI_API_KEY" not in st.secrets: return "Gemini API 키가 설정되지 않았습니다."
    try:
        res = requests.get(image_url)
        img = Image.open(io.BytesIO(res.content))
        
        prompt = """
        이 이미지에서 '차트 캔들 옆에 있는 가격 숫자(예: 69,000.00 등)', '시간 축 숫자', '차트 그림 내부에 적힌 라벨(축적, 조작, 분배 등)'은 완벽하게 무시해줘. 
        오직 차트 위/아래에 작성된 **블로그 본문 설명글, 글머리 기호(불릿 포인트), 문장 형태의 텍스트**만 정확하게 추출해. 
        절대 내용을 요약하거나 너의 의견을 덧붙이지 말고, 원본글의 줄바꿈과 띄어쓰기 양식을 최대한 그대로 유지해서 출력해줘.
        """
        return ask_gemini_dynamic(prompt, img) 
    except Exception as e:
        return f"이미지 다운로드 실패: {e}"

def get_real_ai_advice(image_url, ticker):
    if "GEMINI_API_KEY" not in st.secrets: return "Gemini API 키가 설정되지 않았습니다."
    try:
        res = requests.get(image_url)
        img = Image.open(io.BytesIO(res.content))
        
        prompt = f"이 차트 이미지를 바탕으로 {ticker} 종목에 대한 전문적인 기술적 분석과 트레이딩 조언을 3~4줄로 핵심만 요약해줘. (단, 전문 용어와 숫자가 많더라도 띄어쓰기와 맞춤법을 정확히 지켜서 가독성 좋고 자연스러운 한국어로 작성해줘.)"
        return ask_gemini_dynamic(prompt, img) 
    except Exception as e:
        return f"이미지 다운로드 실패: {e}"

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

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 매매 기록 보관지", "🔎 AI 차트 & 관점 분석", "📚 기본 이론 & DB", "🤖 자동매매 사령실", "📁 분석 자료 아카이브"])

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

# ==============================
# --- Tab 2: 내 관점 분석 ---
# ==============================
with tab2:
    st.header("🔍 AI 차트 분석 및 관점 피드백")
    st.info("차트 스크린샷을 업로드하고 현재 관점을 입력하시면, AI가 '유동성 스윕(Liquidity Sweep)' 등 기본 이론을 바탕으로 정밀 분석해 드립니다.")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        view_uploaded_file = st.file_uploader("📷 차트 이미지 업로드", type=["png", "jpg", "jpeg"], key="view_uploader")
        if view_uploaded_file is not None:
            st.image(view_uploaded_file, caption="업로드된 차트", use_container_width=True)
            
    with col2:
        user_view = st.text_area("✍️ 현재 나의 관점 (예: 1시간봉 전저점 스윕 확인, 롱 진입 대기중)", height=150)
        
        if st.button("🚀 AI 관점 분석 요청", type="primary", use_container_width=True):
            if "GEMINI_API_KEY" not in st.secrets:
                st.error("Gemini API 키가 설정되지 않았습니다.")
            elif view_uploaded_file is not None and user_view:
                with st.spinner('AI가 유동성 스윕 여부와 셋업을 정밀 분석 중입니다... 🤖'):
                    try:
                        img_to_analyze = Image.open(view_uploaded_file)
                        analysis_prompt = f"""
                        당신은 월스트리트 출신의 전문 트레이더이자 나의 트레이딩 멘토입니다. 
                        내가 작성한 [나의 관점]과 첨부된 차트 이미지를 분석해주세요.
                        
                        [나의 관점]: {user_view}

                        특히 '유동성 스윕(Liquidity Sweep)' 이론을 바탕으로 아래 항목을 정밀하게 분석해 주세요.
                        1. 레벨 식별: 차트상 주요 전고점/전저점 등 유동성이 몰려있는 구간 파악
                        2. 스윕 판독: 캔들이 꼬리(Wick)로만 유동성을 찌르고 몸통(Body)은 안착했는지 여부
                        3. 셋업 검증: 현재 진입하기 적합한 기준을 충족했는지 (아니면 관망해야 하는지)
                        4. 멘토 피드백: 나의 관점에 대한 팩트 폭행 및 조언, 기대 손익비(SL/TP) 설정 가이드

                        가독성 좋고 자연스러운 한국어로 출력해주세요.
                        """
                        analysis_result = ask_gemini_dynamic(analysis_prompt, img_to_analyze)
                        
                        st.success("✅ AI 분석 완료!")
                        st.subheader("🤖 AI 멘토의 피드백")
                        st.write(analysis_result)
                        
                    except Exception as e:
                        st.error(f"분석 중 오류가 발생했습니다: {e}")
            else:
                st.warning("⚠️ 차트 이미지 업로드와 나의 관점 텍스트를 모두 입력해 주세요.")

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
        # 카테고리 정렬 (1, 2, 3 순서대로 나오게)
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
# --- Tab 4: 🤖 자동매매 컨트롤 센터 (사령실 디자인) ---
# ==============================
with tab4:
    st.header("🤖 자동매매 사령실 (컨트롤 패널)")
    st.caption("비트겟(Bitget) API 및 트레이딩뷰 Webhook 기반 자동 트레이딩 시스템")
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

    bot_tab1, bot_tab2, bot_tab3 = st.tabs(["⚙️ 기본 세팅 (API)", "🧠 매매 전략 & 웹훅", "📋 실시간 작동 로그"])

    with bot_tab1:
        st.subheader("🔑 거래소 연결 및 자금 관리")
        with st.form("bot_basic_form", border=True):
            st.info("방금 발급받은 비트겟(Bitget) API Key 3종 세트를 입력하세요. (현재는 UI 테스트 상태입니다.)")
            c1, c2 = st.columns(2)
            with c1:
                api_key = st.text_input("Bitget API Key (Access Key)", type="password", placeholder="발급받은 API 키 입력")
                secret_key = st.text_input("Bitget Secret Key", type="password", placeholder="Secret Key 입력")
            with c2:
                api_passphrase = st.text_input("API Passphrase (비밀번호)", type="password", placeholder="설정한 비밀번호 입력")
                leverage = st.slider("기본 레버리지 (x)", min_value=1, max_value=50, value=10)

            st.write("")
            invest_pct = st.select_slider("1회 진입 비중 (총 시드의 %)", options=[5, 10, 15, 20, 25, 50, 100], value=10)
            
            if st.form_submit_button("기본 세팅 저장", type="primary"):
                st.success("API 및 자금 세팅이 임시 저장되었습니다! (추후 로봇 서버 연결 시 연동됩니다.)")

    with bot_tab2:
        st.subheader("🎯 트레이딩뷰 연동 (Webhook) 설정")
        c_hook, c_strat = st.columns([6, 4], gap="large")
        
        with c_hook:
            st.markdown("👇 **트레이딩뷰 얼러트(Alert) 창에 넣을 Webhook URL**")
            st.code("https://youngwoo-trading.streamlit.app/api/webhook", language="text")
            st.markdown("👇 **트레이딩뷰 메시지 양식 (예시)**")
            st.code('{\n  "action": "long",\n  "ticker": "BTCUSDT",\n  "strategy": "OrderBlock"\n}', language="json")
            
        with c_strat:
            st.selectbox("메인 전략 선택", ["트레이딩뷰 알람(Webhook) 전용", "AI 차트 감시 결합형 (베타)"])
            st.checkbox("손절(SL) 도달 시 즉시 시장가 종료 (안전장치)", value=True)
            st.checkbox("반대 신호 발생 시 기존 포지션 스위칭", value=False)
            if st.button("전략 저장", use_container_width=True):
                st.success("전략이 업데이트 되었습니다.")

    with bot_tab3:
        st.subheader("📡 로봇 작동 터미널")
        st.caption("최근 50개의 시스템 로그를 보여줍니다.")
        log_text = """[System] 컨트롤 패널이 정상적으로 활성화되었습니다.
[System] Bitget API 키 대기 중...
[System] 봇 가동 시 이 터미널에 매매 내역이 기록됩니다."""
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
                        with st.spinner("무료 AI(Gemini)가 최적의 모델을 찾아 분석 중입니다... 여러 장을 올리면 시간이 조금 걸립니다! 🤖"):
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
                                        time.sleep(4) 
                            
                            if arch_imgs_detail:
                                for img_file in arch_imgs_detail:
                                    group, sub = get_file_group_info(img_file.name)
                                    url = upload_image_to_supabase(img_file, f"arch_detail_{group}_{sub}")
                                    if url:
                                        detail_urls.append(url)
                                        if img_file.name in selected_charts_for_ai:
                                            ai_advice_final_mapping[group] = get_real_ai_advice(url, arch_ticker1)
                                            time.sleep(4) 

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
