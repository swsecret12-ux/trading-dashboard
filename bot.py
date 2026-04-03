from flask import Flask, request, jsonify
import ccxt
import os
import json # 💡 필수 부품 추가!

app = Flask(__name__)

# 1. 렌더(Render) 금고 열쇠
bitget_api_key = os.environ.get('BITGET_API_KEY')
bitget_secret_key = os.environ.get('BITGET_SECRET_KEY')
bitget_passphrase = os.environ.get('BITGET_PASSPHRASE')

# 2. 비트겟 연결
try:
    exchange = ccxt.bitget({
        'apiKey': bitget_api_key,
        'secret': bitget_secret_key,
        'password': bitget_passphrase,
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
except Exception as e:
    print(f"비트겟 연결 에러: {e}", flush=True)

@app.route('/')
def home():
    return "🚀 비트겟 24시간 자동매매 로봇 가동 중!"

# 💡 [핵심] GET과 POST를 모두 허용해서 우리가 직접 테스트할 수 있게 만듭니다!
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # 👉 1. 브라우저 테스트 (로봇 귀 찌르기)
    if request.method == 'GET':
        print("👀 브라우저 찌르기 테스트 성공! 서버가 완벽하게 살아있습니다.", flush=True)
        return "웹훅 수신 대기중... (정상 작동)", 200

    # 👉 2. 트레이딩뷰 실전 통신
    try:
        # 트레이딩뷰가 텍스트로 보내든 뭐든 '생것(Raw)' 그대로 다 받아오기!
        raw_data = request.data.decode('utf-8')
        print(f"📩 [1단계] 트레이딩뷰 원본 데이터 수신: {raw_data}", flush=True)

        if not raw_data:
            return jsonify({"status": "error", "message": "데이터가 없습니다."}), 400

        # 텍스트를 암호 해독(JSON)
        data = json.loads(raw_data)
        
        action = data.get('action')
        ticker = data.get('ticker')
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            print("❌ 수량 오류: amount 값이 없습니다.", flush=True)
            return jsonify({"status": "error", "message": "수량이 0입니다."}), 400

        symbol = ticker.replace("USDT", "/USDT:USDT")
        print(f"🤖 [2단계] 명령 분석 완료: {symbol} / {action} / {amount}개", flush=True)

        # 비트겟 슛!
        if action == 'long':
            order = exchange.create_market_buy_order(symbol, amount)
            print(f"🟢 [3단계] 롱 진입 성공! 주문 번호: {order['id']}", flush=True)
        elif action == 'short':
            order = exchange.create_market_sell_order(symbol, amount)
            print(f"🔴 [3단계] 숏 진입 성공! 주문 번호: {order['id']}", flush=True)

        return jsonify({"status": "success"}), 200

    except json.JSONDecodeError:
        print("❌ [에러] 트레이딩뷰 메시지가 올바른 JSON(괄호/따옴표) 형식이 아닙니다.", flush=True)
        return jsonify({"error": "JSON 형식 오류"}), 400
    except Exception as e:
        print(f"❌ [주문 에러] {e}", flush=True)
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
