#!/usr/bin/env bash
# 문의 하나(또는 한 묶음)가 도착했을 때 요청 하나를 처리한다 — scripts/watch.sh 가 inbox/ 의 파일마다 부른다.
#
#   scripts/request.sh inbox/T-1041.json       도착한 문의 파일 하나
#   scripts/request.sh --case case-01-mixed    연습 요청(케이스의 문의 넷, 열 때마다 새 번호)
#   scripts/request.sh --dry-run <위와 같이>    부를 명령만 찍는다(요청도 열지 않는다)
#
# 순서: 요청 열기(같은 문의가 이미 처리됐으면 건너뜀) → claude -p "/handle-request <요청 id>" → 마무리.
# 끝날 때 신호: 0 전부 팀 큐(routed) · 3 사람 차례(escalated — 일부가 사람 큐, 정상 / needs_human) · 1 실패 · 건너뛰면 0.
# 처리한 문의 파일(건너뛴 중복 포함)은 inbox/done/ 으로 옮긴다 — 다음 확인 때 다시 보지 않게.
#
# cron 에는 터미널도 로그인한 사람의 PATH 도 없다. 그래서 첫 줄에서 이 프로젝트 폴더로 들어가고
# (이 폴더의 .claude/ 만 걸리게), claude 를 찾을 곳을 PATH 에 채운다.
# --bare 는 붙이지 않는다 — 차단 장치(보호·검수·다음 단계)가 모두 꺼진다. tests/test_scripts.py 가 본다.
set -u
cd "$(dirname "$0")/.." || exit 64
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
# -p 실행에서는 하위 에이전트가 기본으로 백그라운드에서 돈다(공식 문서). 끝날 때까지 기다리게 끈다 — guard.py 도 막는다.
export CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
# 한 번 부른 Claude 가 10분을 넘기면 끊는다. 운영체제마다 다른 timeout 명령 대신 파이썬으로 건다(scripts/limited.py).

DRY=0; FILE=""; CASE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --case) CASE="$2"; shift ;;
    -*) echo "쓰는 법: scripts/request.sh [--dry-run] <inbox/문의.json | --case 케이스>"; exit 64 ;;
    *) FILE="$1" ;;
  esac
  shift
done
if [ -z "$FILE" ] && [ -z "$CASE" ]; then
  echo "쓰는 법: scripts/request.sh [--dry-run] <inbox/문의.json | --case 케이스>"; exit 64
fi

if [ -n "$FILE" ]; then
  if ! RID=$(uv run python scripts/open_request.py --id-for "$FILE"); then
    echo "$RID"
    # 읽을 수 없는 파일은 inbox/bad/ 로 옮긴다 — 매분 같은 오류를 되풀이하지 않게(사람이 본다)
    case "$FILE" in inbox/done/*|inbox/bad/*) ;; inbox/*) [ $DRY -eq 1 ] || { mkdir -p inbox/bad && mv -f "$FILE" inbox/bad/; } ;; esac
    exit 64
  fi
  OPEN=(--event "$FILE")
else
  RID="$CASE-<번호>"
  OPEN=(--case "$CASE")
fi

CMD=handle-request
# Claude 를 부르는 옵션은 이 함수 한 곳에 둔다(네 프로젝트가 같은 모양). CMD 는 부를 명령 이름이다.
claude_args() {
  # 본 에이전트의 모델: 구독에 맞춰 환경 변수 ANTHROPIC_MODEL 로 고른다(Pro 는 sonnet, Max 는 opus). 없으면 sonnet.
  # 자동 실행은 --setting-sources project 라 대화 창에서 /model 로 저장한 값을 읽지 않는다 — 그래서 여기서 따로 받는다.
  # 하위 에이전트 drafter 는 .claude/agents/drafter.md 의 model: sonnet(가벼운 일은 가벼운 모델)을 그대로 쓴다.
  MODEL="${ANTHROPIC_MODEL:-sonnet}"
  # 계정에 연결한 커넥터(MCP — 메일·캘린더 같은)는 설정 파일이 아니라 계정에 붙어 있어 --setting-sources 로 빠지지 않는다.
  # 이 실행은 쓰지 않는데 도구 목록이 부를 때마다 문맥에 통째로 실리니 --strict-mcp-config 로 뺀다.
  CLAUDE_ARGS=(-p "/$CMD $1" --model "$MODEL" --setting-sources project --strict-mcp-config --permission-mode dontAsk
    --tools "Read,Write,Agent,Bash"
    --allowedTools "Read,Write,Agent,Task,Bash(uv run python scripts/open_request.py:*)"
    --output-format json)
}

if [ $DRY -eq 1 ]; then
  claude_args "$RID"
  echo "(dry-run) 요청 열기: uv run python scripts/open_request.py ${OPEN[*]}"
  echo "(dry-run) 작성이 필요하면: REQUEST_ID=$RID uv run python scripts/limited.py 600 $CLAUDE_BIN ${CLAUDE_ARGS[*]}"
  echo "(dry-run) 마무리: uv run python scripts/open_request.py --finish $RID"
  exit 0
fi

mkdir -p requests
if [ -n "$FILE" ] && command -v flock >/dev/null 2>&1; then
  # 같은 문의를 두 실행이 동시에 잡지 않게 — 앞 실행이 아직 돌고 있으면 건드리지 않고 나간다.
  # (flock 이 없는 macOS 에서는 이 줄이 빠진다. 요청 폴더 선점(mkdir)은 그대로 걸린다.)
  exec 9>"requests/.$RID.lock"
  flock -n 9 || { echo "busy: $RID 은 다른 실행이 처리 중이다"; exit 0; }
fi

done_file() {
  case "$FILE" in
    inbox/done/*) ;;
    inbox/*) mkdir -p inbox/done && mv -f "$FILE" inbox/done/ ;;
  esac
}

out=$(uv run python scripts/open_request.py "${OPEN[@]}"); code=$?
echo "$out" | grep -v '^REQUEST_ID=' | head -1
if [ $code -eq 10 ]; then done_file; exit 0; fi   # 이미 처리한 문의 — Claude 를 부르지 않는다
echo "$out" | grep -q '^REQUEST_ID=' || exit "$code"
RID=$(echo "$out" | sed -n 's/^REQUEST_ID=//p' | tail -1)

if [ $code -eq 0 ]; then
  claude_args "$RID"
  REQUEST_ID="$RID" uv run python scripts/limited.py 600 "$CLAUDE_BIN" "${CLAUDE_ARGS[@]}" \
    > "requests/$RID/claude.json" 2> "requests/$RID/claude.err"
fi
uv run python scripts/open_request.py --finish "$RID"; code=$?
done_file
exit $code
