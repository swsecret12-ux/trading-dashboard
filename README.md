# Youngwoo Trading Dashboard

Streamlit 기반의 개인 투자 연구 대시보드입니다.

## ChatGPT 개인 플러그인

`mcp_server.py`는 기존 대시보드의 Supabase 기록을 ChatGPT에서 조회할 수 있게 하는
별도 읽기 전용 MCP 서버입니다. 실거래 주문이나 자동매매 도구는 포함하지 않습니다.

설치와 연결 방법은 [개인 플러그인 설정 안내](docs/PERSONAL_PLUGIN_SETUP.md)를 참고하세요.

TradingView 차트는 ChatGPT 대화에 스크린샷으로 첨부하고, 연결된 플러그인의 읽기 전용
기술지표와 함께 분석할 수 있습니다. MCP 서버는 OpenAI API를 별도로 호출하지 않으므로
저장소에 OpenAI API 키가 필요하지 않습니다.
