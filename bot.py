from flask import Flask, request, jsonify
import ccxt
import os

app = Flask(__name__)

# 1. 렌더(Render) 금고에 숨겨둔 비트겟 열쇠 가져오기
bitget_api_key = os.environ.get('BITGET_API_KEY')
bitget_secret_key = os.environ.get('BITGET_SECRET_KEY')
bitget_passphrase = os.environ.get('BITGET_PASSPHRASE')

# 2. 비트겟(Bitget) 거래소 무기 장착 (선물 거래용 세팅)
exchange = ccxt.bitget({
    'apiKey': bitget_api_key,
    'secret': bitget_secret_key,
    'password': bitget_passphrase,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
    }
})

@app.route('/')
def home():
    return "🚀 비트겟 24시간 자동매매 로봇 가동 중!"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # 💡 [핵심 수정] 트레이딩뷰의 텍스트 포장지를 강제로 찢고 JSON으로 읽어옵니다!
        data = request.get_json(force=True)
        print(f"📩 트레이딩뷰 신호 수신: {data}", flush=True) # flush=True 로 터미널에 즉시 출력!
        
        action = data.get('action')
        ticker = data.get('ticker')
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            print("❌ 수량 오류: amount 값이 없거나 0입니다.", flush=True)
            return jsonify({"status": "error", "message": "수량이 0입니다."}), 400

        # 3. 비트겟 전용 선물 종목 이름으로 변환 (예: XRPUSDT -> XRP/USDT:USDT)
        symbol = ticker.replace("USDT", "/USDT:USDT")
        
        print(f"🤖 [명령 하달] {symbol} 종목 {action} 방향으로 {amount}개 시장가 진입 시도!", flush=True)

        # 4. 롱/숏 시장가 주문 때리기!
        if action == 'long':
            order = exchange.create_market_buy_order(symbol, amount)
            print(f"🟢 [롱 진입 성공] 주문 번호: {order['id']}", flush=True)
        elif action == 'short':
            order = exchange.create_market_sell_order(symbol, amount)
            print(f"🔴 [숏 진입 성공] 주문 번호: {order['id']}", flush=True)
        else:
            print("❌ 알 수 없는 포지션 방향입니다.", flush=True)

        return jsonify({"status": "success", "message": "주문 쏴버렸습니다!"}), 200

    except Exception as e:
        # 💡 에러가 나면 숨기지 말고 무조건 즉시 출력하게 만듭니다.
        print(f"❌ [주문 에러 발생] {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
