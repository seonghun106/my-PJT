# TradingView 공개 차트 관찰 기록

작성일: 2026-10-19 · 도구: REA (`rea-agents` 6.7.0)

## 요약

이번 작업 환경(클라우드 컨테이너)에서는 TradingView에 접속할 수 없어 **실제 관찰을 하지 못했습니다.**
아래 "구현에 쓴 가정"은 관찰로 확인한 사실이 아닙니다. 모두 미확인 항목입니다.
로그인, 유료 기능, 원본 코드, 이미지는 사용하거나 복사하지 않았습니다.

## 환경과 REA 연결

| 항목 | 값 |
| --- | --- |
| 운영체제 | Ubuntu 24.04.5 LTS (x86_64), 클라우드 컨테이너 |
| Node.js / npm | v22.22.0 / 10.9.4 (REA 요구: 22.x ≥ 22.19) |
| 브라우저 | Playwright Chromium (`/opt/pw-browsers/chromium-1194`) |
| 코딩 에이전트 | Claude Code |
| REA 설정 | `npx rea-agents@6.7.0 setup --client claude_code` → `/root/.claude.json`에 `mcpServers.rea` 등록, 스킬 `~/.claude/skills/reverse-engineer-anything` 설치 |
| 연결 점검 | `claude mcp list` → `rea: npx -y rea-agents@6.7.0 mcp - ✓ Connected`, doctor: registration `aligned`, skill `aligned` (도구 207개) |

## 관찰 시도와 결과 (근거)

| 시각(UTC) | 시도 | 결과 |
| --- | --- | --- |
| 03:12 | `curl https://www.tradingview.com/chart/?symbol=NASDAQ%3AMU` | 프록시 `CONNECT tunnel failed, response 403` |
| 03:12 | `curl https://www.tradingview.com/symbols/NASDAQ-MU/` | 같은 403 |
| 03:13 | Yahoo, Stooq, Nasdaq, Google | 모두 연결 불가. npm 레지스트리만 허용됨 |

REA의 웹 관찰(`list-browser-targets`, `inspect-web-page`, `observe-web-session`)은 사용자가 띄운 브라우저 페이지에 붙어 동작합니다.
페이지를 열 수 없어 관찰 단계는 진행하지 못했습니다.

## 미확인 항목

| 항목 | 구현에 쓴 가정 (미확인) |
| --- | --- |
| 종목 전환 | 입력칸에서 종목 코드를 바꾸면 차트 전체를 새로 불러옴. URL에 종목을 남김 |
| 주기 전환 | 일·주·월 버튼. 같은 가격 데이터를 다시 묶고 지표도 해당 주기 기준으로 다시 계산 |
| 지표 표시 | 이동평균은 가격 패널 위에, RSI는 아래 별도 패널에 30/70 기준선과 함께 표시 |
| 지표 값 표시 | 커서 위치 봉의 OHLC와 지표 값을 차트 위 범례 줄에 표시 |
| 확대·이동 | 휠로 확대·축소, 드래그로 이동 |
| 네트워크 | 종목·주기 전환 시 어떤 요청이 오가는지 (확인 못함) |

## 직접 관찰하려면 (본인 PC에서)

인터넷이 되는 PC에서 아래 순서로 실행하면 위 항목을 확인할 수 있습니다. 로그인하지 않은 공개 페이지만 보세요.

```bash
# 1) 전용 프로필로 브라우저 실행 (디버깅 포트는 127.0.0.1에만 열림)
chromium --remote-debugging-port=9222 --user-data-dir=/tmp/rea-browser-profile \
  "https://www.tradingview.com/chart/?symbol=NASDAQ%3AMU"

# 2) 페이지 찾기
npx -y rea-agents@6.7.0 list-browser-targets http://127.0.0.1:9222 \
  --allowed-origins https://www.tradingview.com --json

# 3) 구조와 리소스 기록
npx -y rea-agents@6.7.0 inspect-web-page http://127.0.0.1:9222 <TARGET_ID> --observation-ms 1000 --json

# 4) 관찰 창을 열어 둔 상태에서 손으로 종목·주기·지표를 바꾸기
npx -y rea-agents@6.7.0 observe-web-session http://127.0.0.1:9222 <TARGET_ID> --observation-ms 30000 --json
```

결과에는 근거(Evidence ID)가 붙습니다. 이 결과로 위 표의 "가정"을 확인하거나 고치면 됩니다.
