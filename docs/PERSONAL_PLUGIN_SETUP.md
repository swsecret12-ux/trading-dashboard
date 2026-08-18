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
| `build_trade_review_context` | 일지와 관련 분석을 복기용으로 묶기 |

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
