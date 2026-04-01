from flask import Flask, request, jsonify
import ccxt
import os

app = Flask(__name__)

# 💡 비트겟 API 키는 코드에 직접 적지 않고, 나중에 클라우드 서버(Render) 환경변수에 안전하게 숨겨둘 겁니다!
BITGET_API_KEY = os.environ.get('BITGET_API_KEY')
BITGET_SECRET_KEY = os.environ.get('BITGET_SECRET_KEY')
BITGET_PASSPHRASE = os.environ.get('BITGET_PASSPHRASE')

# 서버가 잘 켜져 있는지 확인하는 기본 주소
@app.route('/')
def home():
    return "🚀 자동매매 봇 서버가 24시간 정상 가동 중입니다!"

# 트레이딩뷰에서 알람(Webhook)을 받을 전용 주소
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        print(f"📩 트레이딩뷰 신호 수신 완료: {data}")
        
        # --- (이곳에 나중에 비트겟 매수/매도 로직이 추가될 예정입니다) ---
        ticker = data.get('ticker')
        action = data.get('action')
        
        # 터미널에 로그 찍기
        print(f"실행 명령: {ticker} 종목 {action} 포지션 진입!")
        
        return jsonify({"status": "success", "message": "신호 수신 및 처리 완료"}), 200

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    # 클라우드 서버 포트에 맞춰 24시간 대기 모드 실행
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
