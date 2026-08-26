# ChatGPT 개인용 플러그인 설정

이 구성은 기존 Streamlit 앱을 대체하지 않습니다. 같은 저장 데이터를 읽는 별도 MCP
서버를 배포하고, ChatGPT의 개인 플러그인으로 연결합니다.

## 동작 구조

1. ChatGPT가 공개 HTTPS 주소의 `/mcp`로 필요한 조회 도구를 호출합니다.
2. MCP 서버가 GitHub OAuth 로그인을 요구합니다.
3. 로그인 계정이 배포 환경의 `MCP_ALLOWED_GITHUB_LOGIN`과 일치할 때만 Supabase 데이터를 읽습니다.
4. 반환된 기록은 현재 ChatGPT 대화 모델이 분석합니다.

MCP 서버에는 쓰기·삭제·주문 기능이 없습니다. `bot.py`도 가져오거나 호출하지 않습니다.
저장소에 OpenAI API 키를 추가할 필요가 없고, Gemini API를 호출하지도 않습니다.

## 제공 도구

| 도구 | 용도 |
|---|---|
| `dashboard_status` | 저장 영역 연결 상태 확인 |
| `list_recent_trades` | 최근 매매일지 조회 |
| `get_trade_detail` | 개별 매매 기록 조회 |
| `search_analysis_archive` | 분석 아카이브 검색 |
| `list_watchlist` | `나의관점`으로 저장한 관심종목 기록 조회 |
| `list_sector_research` | 섹터·기업 리서치 조회 |
| `get_trading_theories` | 기본·사용자 이론 노트 조회 |
| `get_market_snapshot` | 중립적인 과거 시장 통계 조회 |
| `get_chart_analysis_context` | 첨부 차트와 대조할 기술지표·최근 봉 조회 |
| `build_trade_review_context` | 일지와 관련 분석을 복기용으로 묶기 |

`get_chart_analysis_context`는 EMA·SMA·RSI·MACD·볼린저밴드·ATR·거래량 비교와
최근 OHLCV 봉을 계산합니다. 최근 고가·저가는 확정 지지·저항이 아닌 단순 참고 범위로만
표시합니다. 이 도구도 주문, 저장, 수정 기능이 없는 읽기 전용 도구입니다.

## 1. GitHub OAuth 앱 만들기

GitHub의 **Settings → Developer settings → OAuth Apps → New OAuth App**에서 다음 값을
설정합니다.

- Homepage URL: 배포 서비스의 기본 주소. 예: `https://youngwoo-trading-mcp.example.com`
- Authorization callback URL: 기본 주소 뒤에 `/oauth/auth/callback`을 붙인 주소

발급된 Client ID와 Client Secret은 아래 배포 환경변수에만 넣습니다. 저장소나 Streamlit
Secrets에 복사하지 않습니다.

## 2. MCP 서버 배포

저장소의 `render.yaml`은 Python 웹 서비스 배포 예시입니다. 다른 Python 호스팅을 써도
되지만, 외부에서 접근 가능한 HTTPS 주소와 지속 실행되는 프로세스가 필요합니다.

필수 환경변수:

| 변수 | 값 |
|---|---|
| `MCP_AUTH_MODE` | `github` |
| `MCP_BASE_URL` | 배포 서비스의 기본 HTTPS 주소. `/mcp` 제외 |
| `MCP_ALLOWED_GITHUB_LOGIN` | 접속을 허용할 본인의 GitHub 로그인 이름 |
| `MCP_JWT_SIGNING_KEY` | 충분히 긴 임의 문자열. 배포 서비스에서 생성 |
| `GITHUB_CLIENT_ID` | GitHub OAuth 앱의 Client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth 앱의 Client Secret |
| `SUPABASE_URL` | 현재 Streamlit Secrets와 같은 프로젝트 URL |
| `SUPABASE_PUBLISHABLE_KEY` | 현재 공개/anon 키. 가능하면 최신 publishable key 사용 |
| `SUPABASE_DATA_TOKEN` | 선택 사항. 별도 읽기 전용 RLS 역할의 JWT를 사용할 때 설정 |

배포 서비스의 기본 주소가 결정되면 GitHub OAuth 앱의 Homepage와 callback URL을 그
주소로 다시 확인해야 합니다. Supabase 프로젝트가 일시중지 상태라면 먼저 프로젝트를
정상 상태로 복구해야 조회가 됩니다.

`render.yaml`은 MCP 서비스에 Python 3.13.5를 지정하고, 사용자 로그인 이름과 모든
비밀정보는 Render 환경변수로만 받습니다. `requirements-mcp.txt`는 MCP 서버에 필요한
패키지만 고정 버전으로 설치하므로 기존 Streamlit 대시보드의 `requirements.txt`와
독립적입니다.

OAuth의 자동 클라이언트 등록·로그인·콜백 경로는 호스팅 서비스와의 루트 경로 충돌을
피하기 위해 `/oauth/*` 아래에서 제공됩니다. ChatGPT에 입력하는 MCP 주소는 계속
`https://배포한-주소/mcp`이며 변경되지 않습니다.

### Supabase 읽기 전용 권한 권고

코드 자체는 허용된 테이블과 컬럼에 대한 HTTP GET 요청만 만들지만, 운영 환경에서는
데이터베이스 권한도 별도로 제한하는 것이 안전합니다. 기존 대시보드가 같은 anon 역할로
쓰기 작업을 사용한다면 그 역할의 쓰기 정책을 제거하면 대시보드가 손상됩니다. 대신 MCP
전용 Postgres/RLS 읽기 역할과 JWT를 발급해 `SUPABASE_DATA_TOKEN`에 넣고, 다음 네 테이블의
SELECT만 허용하세요.

- `trade_history`
- `analysis_archive`
- `sector_analysis`
- `theory_db`

MCP 전용 역할에는 INSERT, UPDATE, DELETE 및 Storage 쓰기 권한을 주지 않습니다. JWT와
Supabase 서명 비밀은 저장소에 커밋하지 말고 Render 환경변수에만 저장합니다.

## 3. ChatGPT에 연결

ChatGPT에서 **Settings → Security and login → Developer mode**를 활성화합니다. 계정이나
워크스페이스 정책에 따라 Developer mode가 보이지 않을 수 있습니다. 그다음
[ChatGPT Plugins](https://chatgpt.com/plugins)의 추가 버튼에서 표시 이름과 설명을 입력하고,
Connection에 다음 MCP 서버 주소를 입력합니다.

```text
https://배포한-주소.example.com/mcp
```

연결을 만들 때 검색된 도구 이름, 설명, 입력 스키마와 읽기 전용 표시를 확인합니다. GitHub
로그인 화면이 열리면 허용된 계정으로 승인합니다. 이후 개인 Plugins 목록에서 설치한 뒤
새 Work 대화에서 `@`를 입력해 플러그인을 선택할 수 있습니다.

예시 질문:

- 최근 저장 기록 5건에서 반복되는 실수만 요약해 주세요.
- 관심종목 기록과 분석 아카이브 사이에서 서로 모순되는 관점을 찾아 주세요.
- AAPL의 3개월 시장 통계와 저장된 리서치가 어떻게 다른지 비교해 주세요.

결과는 연구와 기록 정리를 위한 참고 자료이며, 매수·매도 지시나 수익 보장이 아닙니다.

## TradingView 차트를 현재 ChatGPT 모델로 분석하기

이 방식에서는 MCP 서버가 AI 모델을 실행하지 않습니다. 대화에서 선택한 ChatGPT 모델이
사용자가 첨부한 이미지와 MCP의 수치 데이터를 함께 분석합니다. 따라서 별도의 OpenAI API
키나 API 사용료가 생기는 구현은 포함하지 않습니다. 다만 ChatGPT 구독, Render 요금제 및
인터넷 데이터 제공 조건은 각 서비스의 현재 정책을 따릅니다.

1. TradingView에서 종목명, 거래소, 시간봉, 마지막 봉 시점이 보이도록 차트를 캡처합니다.
2. ChatGPT에서 이 개인 플러그인을 활성화한 새 대화를 열고 차트 이미지를 첨부합니다.
3. 프롬프트에 종목 코드와 시간봉을 텍스트로도 적습니다. 이미지 글자가 흐리면 모델이 다른
   종목이나 시간봉으로 오인할 수 있습니다.
4. 플러그인의 `get_chart_analysis_context`를 사용해 같은 종목·시간봉의 수치와 교차 검증해
   달라고 요청합니다.

미국 주식 일봉 예시:

```text
첨부한 TradingView 차트는 NASDAQ:AAPL 일봉입니다.
Youngwoo Trading MCP의 get_chart_analysis_context를 AAPL, 6mo, 1d로 조회해서
차트 이미지와 수치를 교차 검증해 주세요.
추세, 모멘텀, 변동성, 거래량, 최근 고가·저가 참고 범위를 구분해서 설명하고,
이미지에서 확실하지 않은 내용과 데이터 시점 차이도 명시해 주세요.
매수·매도 지시는 하지 마세요.
```

시간봉 예시:

```text
첨부 차트는 MSFT 1시간봉입니다. get_chart_analysis_context를 MSFT, 1mo, 1h로
조회한 뒤 보이는 구조와 수치가 일치하는지 분석해 주세요. 최신 봉 시각을 먼저 비교하고,
불일치하면 그 이유만 설명해 주세요.
```

TradingView 계정 화면을 MCP가 직접 조작하거나 차트 이미지를 자동으로 가져오는 연결은
아닙니다. 이미지는 사용자가 대화에 첨부하고, 시장 수치는 `yfinance`를 통해 별도로 조회하므로
TradingView와 가격 조정 방식, 거래소 세션, 지연 시간에 따라 값이 조금 다를 수 있습니다.
ChatGPT가 이미지를 읽는 기능과 MCP 도구 사용은 서로 분리되어 있으며, MCP가 차트를 직접
보았다고 간주하면 안 됩니다. 한국 종목은 `005930.KS`, 가상자산은 `BTC-USD`처럼 Yahoo
Finance 형식의 종목 코드를 사용해야 하며, 50개 미만의 봉이 조회되면 장기 이동평균 해석에
데이터 부족 경고가 함께 반환됩니다.

## 로컬 검증

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-mcp.txt
python -m unittest discover -s tests -v
```

Windows PowerShell에서는 활성화 명령으로 `.\.venv\Scripts\Activate.ps1`을 사용합니다.
배포 전에 MCP Inspector에서 Streamable HTTP 주소 `http://localhost:8000/mcp`를 열어 도구
검색, 인증 실패, 정상 호출과 빈 결과를 각각 확인하는 것도 권장합니다.

로컬 HTTP 테스트에는 `MCP_AUTH_MODE=static`과 24자 이상의 `MCP_STATIC_TOKEN`을 사용할
수 있지만, 인터넷에 공개되는 배포 환경에서는 반드시 `github` 모드를 사용합니다.

## 공식 문서

- OpenAI Plugins quickstart: https://developers.openai.com/plugins/quickstart
- MCP server 만들기: https://developers.openai.com/plugins/build/mcp-server
- ChatGPT 연결 및 테스트: https://developers.openai.com/plugins/deploy/connect-chatgpt
- 인증: https://developers.openai.com/plugins/build/auth
