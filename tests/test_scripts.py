"""시작 스크립트 시험 — 가짜 claude 로, 모델을 부르지 않는다.

    uv run python tests/test_scripts.py

  1. request.sh 에 --bare 가 없다(붙이면 차단 장치가 모두 꺼진다)
  2. request.sh 가 이 프로젝트 폴더로 들어가고 --setting-sources project 로 개인 설정을, --strict-mcp-config 로 계정의 커넥터를 뺀다
  3. --dry-run 은 부를 claude -p 줄만 찍고 요청을 열지 않는다
  4. inbox/ 에 문의가 오면 claude 를 한 번 부르고, 분류가 쓰이면 검수·전달까지 가서 큐에 넣는다
     (가짜 claude 가 drafter 대신 저장된 분류를 쓴다 — 차단 장치는 부르지 않으니 마무리가 흐름을 민다)
  5. 같은 문의가 한 번 더 배달되면 Claude 를 부르지 않고 건너뛴다(요청 폴더를 먼저 만든 쪽 하나만)
  6. inbox/ 가 비어 있으면 watch.sh 는 아무것도 부르지 않는다
전부 맞으면 0.

보장하지 않는 것: 실제 claude 가 이 인자로 차단 장치를 부른다는 것 — 그것은 실제 실행으로 본다.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
fails = []


def ok(cond: bool, what: str) -> None:
    print(f"{'OK  ' if cond else 'FAIL'} {what}")
    if not cond:
        fails.append(what)


def main() -> int:
    for s in (sys.stdout,):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    sh = (SRC / "scripts" / "request.sh").read_text(encoding="utf-8")
    code_lines = [l for l in sh.splitlines() if not l.lstrip().startswith("#")]
    ok(not any("--bare" in l for l in code_lines), "request.sh 에 --bare 가 없다")
    ok('cd "$(dirname "$0")/.."' in sh, "request.sh 가 이 프로젝트 폴더로 들어간다")
    ok("--setting-sources project" in sh, "request.sh 가 개인 설정을 뺀다(--setting-sources project)")
    ok("--strict-mcp-config" in sh, "request.sh 가 계정의 커넥터를 싣지 않는다(--strict-mcp-config)")
    with tempfile.TemporaryDirectory(prefix="scripts-") as t:
        root = Path(t) / "triage"
        shutil.copytree(SRC, root, ignore=shutil.ignore_patterns("requests", "assignments", "inbox", "logs",
                                                                  "__pycache__"))
        # 문의 한 건짜리 파일과, drafter 가 썼을 분류(저장된 표본에서 그 한 건)
        tickets = json.loads((SRC / "cases" / "tickets" / "2026-08-31.json").read_text(encoding="utf-8"))
        one = {"received_date": tickets["received_date"], "tickets": [tickets["tickets"][0]]}
        sample = json.loads((SRC / "samples" / "reference" / "case-01-mixed.json").read_text(encoding="utf-8"))
        draft = Path(t) / "draft.json"
        draft.write_text(json.dumps({"classifications": sample["classifications"][:1]}, ensure_ascii=False),
                         encoding="utf-8")
        log = Path(t) / "claude-calls.log"
        fake = Path(t) / "claude"
        fake.write_text(f"#!/bin/sh\necho \"$@\" >> {log}\n"
                        f"cp {draft} \"requests/$REQUEST_ID/draft.json\"\necho '{{}}'\n", encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        # 임시 폴더는 꾸러미 밖이라 uv 가 .venv 를 못 찾는다 — 지금 이 시험을 실행한 가상환경을 알려 준다
        env = dict(os.environ, CLAUDE_BIN=str(fake), PYTHONUTF8="1", VIRTUAL_ENV=sys.prefix)
        env.pop("REQUEST_ID", None)
        run = lambda *a: subprocess.run(["bash", *a], cwd=root, env=env,
                                        capture_output=True, text=True, encoding="utf-8")
        calls = lambda: log.read_text(encoding="utf-8").count("/handle-request") if log.exists() else 0

        def arrive() -> None:
            (root / "inbox").mkdir(exist_ok=True)
            (root / "inbox" / "T-1041.json").write_text(json.dumps(one, ensure_ascii=False), encoding="utf-8")

        arrive()
        p = run("scripts/request.sh", "--dry-run", "inbox/T-1041.json")
        ok(p.returncode == 0 and "claude" in p.stdout and "-p /handle-request issue-T-1041" in p.stdout,
           "--dry-run 은 부를 줄만 찍는다 (-p /handle-request issue-T-1041)")
        ok(not (root / "requests" / "issue-T-1041").exists() and (root / "inbox" / "T-1041.json").exists(),
           "--dry-run 은 요청을 열지 않고 문의 파일도 그대로 둔다")

        p1 = run("scripts/request.sh", "inbox/T-1041.json")
        st = json.loads((root / "requests" / "issue-T-1041" / "state.json").read_text(encoding="utf-8"))
        ok(calls() == 1, "문의가 오면 claude 를 한 번 부른다")
        ok(st.get("terminal") == "routed" and p1.returncode == 0 and "done: routed" in p1.stdout,
           "분류가 쓰이면 검수·전달까지 가서 routed (신호 0)")
        ok(len(list((root / "assignments").glob("*.json"))) == 1, "담당 기록이 한 장 생긴다")
        ok((root / "inbox" / "done" / "T-1041.json").exists() and not (root / "inbox" / "T-1041.json").exists(),
           "처리한 문의 파일은 inbox/done/ 으로 옮긴다")

        arrive()                                        # 같은 문의가 한 번 더 배달됐다
        p2 = run("scripts/watch.sh")
        ok(calls() == 1 and "skip: already processed issue-T-1041 (routed)" in p2.stdout,
           "같은 문의 둘째 배달은 부르지 않고 건너뛴다 (skip: already processed issue-T-1041)")
        ok(not (root / "inbox" / "T-1041.json").exists(), "건너뛴 중복 파일도 inbox/done/ 으로 옮긴다")

        p3 = run("scripts/watch.sh")
        ok(calls() == 1 and p3.returncode == 0, "inbox/ 가 비어 있으면 아무것도 부르지 않는다")
    print("\n스크립트 시험: " + ("통과" if not fails else f"{len(fails)}건 다름"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
