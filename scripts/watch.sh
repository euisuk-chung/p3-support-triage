#!/usr/bin/env bash
# inbox/ 를 한 번 훑어 새 문의 파일마다 scripts/request.sh 를 부른다 — cron 이 매분 부른다.
#
#   scripts/watch.sh             한 번 훑고 끝
#   scripts/watch.sh --dry-run   무엇을 부를지만 찍는다
#
# 시작 계기는 일정이 아니라 **사건**(문의 파일이 생김)이다. cron 은 "사건이 있었나" 를 매분 볼 뿐이고,
# 파일이 없으면 아무것도 부르지 않는다(모델 호출 0). 같은 문의가 두 번 배달돼도 request.sh 가 건너뛴다.
# 앞 확인이 아직 돌고 있으면(요청 하나에 몇 분 걸린다) 이번 확인은 건너뛴다.
set -u
cd "$(dirname "$0")/.." || exit 64
mkdir -p inbox requests
DRY=""; [ "${1:-}" = "--dry-run" ] && DRY="--dry-run"

if command -v flock >/dev/null 2>&1; then
  exec 8>"requests/.poll.lock"
  flock -n 8 || { echo "busy: 앞 확인이 아직 돈다"; exit 0; }
fi

for f in inbox/*.json; do
  [ -e "$f" ] || continue
  scripts/request.sh $DRY "$f"
done
exit 0
