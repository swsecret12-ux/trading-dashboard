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
        'defaultType': 'swap', # 현물이 아닌 선물(Futures) 거래로 설정!
    }
})

@app.route('/')
def home():
    return "🚀 비트겟 24시간 자동매매 로봇 가동 중!"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        print(f"📩 트레이딩뷰 신호 수신: {data}")
        
        action = data.get('action')   # 'long' 또는 'short'
        ticker = data.get('ticker')   # 'XRPUSDT' 등
        amount = float(data.get('amount', 0)) # 구매할 코인 수량 (예: 10)
        
        if amount <= 0:
            return jsonify({"status": "error", "message": "수량이 0이거나 설정되지 않았습니다."}), 400

        # 3. 비트겟 전용 선물 종목 이름으로 변환 (예: XRPUSDT -> XRP/USDT:USDT)
        symbol = ticker.replace("USDT", "/USDT:USDT")
        
        print(f"🤖 [명령 하달] {symbol} 종목 {action} 방향으로 {amount}개 시장가 진입 시도!")

        # 4. 롱/숏 시장가 주문 때리기!
        if action == 'long':
            order = exchange.create_market_buy_order(symbol, amount)
            print(f"🟢 [롱 진입 성공] 주문 번호: {order['id']}")
        elif action == 'short':
            order = exchange.create_market_sell_order(symbol, amount)
            print(f"🔴 [숏 진입 성공] 주문 번호: {order['id']}")
        else:
            print("알 수 없는 포지션 방향입니다.")

        return jsonify({"status": "success", "message": "주문 쏴버렸습니다!"}), 200

    except Exception as e:
        print(f"❌ [주문 에러 발생] {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
