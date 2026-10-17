"""훅이 **무엇을 막고 무엇을 못 막는가.**

    uv run python tests/test_hook.py

장치를 사람마다 다르게 지어도 통과할 수 있게, 이 시험은 **끝날 때 신호(2 막음 · 0 통과)와
행동만** 본다. 장치 안의 변수 이름이나 이유 문장의 글자는 보지 않는다.

## 알려진 통과를 고정한다

이 훅은 **경계가 아니라 가드레일**이다. 그런데 "네 경로를 막았다" 를 반복하다 보면
범위가 슬금슬금 부풀어 경계처럼 말하게 된다.

> **못 막는 것을 실행 가능한 테스트로 박아 둔다.**
> 그래야 다음에 "이제 안전하다" 고 말하지 않는다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "protect_sources.py"

failures: list[str] = []


# 계획서 7절의 "지키는 것" 가운데 하나. 장치 안에서 어떤 이름으로 적었든 이 경로는 막혀야 한다.
PROTECTED_DIR_SAMPLE = "cases/sources"
# 장치가 맡는 도구 — Claude Code 의 쓰기 도구와 셸
HANDLED_TOOLS = ("Bash", "Edit", "NotebookEdit", "Write")


def run(payload: dict) -> int:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload), text=True,
        encoding="utf-8", errors="replace",     # 자식이 CP949 로 써도 읽는다
        capture_output=True,
        env={**os.environ, "PYTHONUTF8": "1"},   # 자식도 UTF-8 로 쓰게 한다
    )
    return proc.returncode


def expect(label: str, payload: dict, blocked: bool) -> None:
    code = run(payload)
    got = code == 2
    good = got == blocked
    if not good:
        failures.append(label)
    want = "막아야" if blocked else "통과해야"
    print(f"   {'OK  ' if good else 'FAIL'} exit={code}  {want} | {label}")


def blocks() -> None:
    print("1. 막는 것 — 대화형에서 흔한 실수")
    expect("Write cases/sources/", {"tool_name": "Write",
           "tool_input": {"file_path": "cases/sources/x.txt"}}, True)
    expect("NotebookEdit (notebook_path)", {"tool_name": "NotebookEdit",
           "tool_input": {"notebook_path": "cases/sources/x.ipynb"}}, True)
    expect("Bash 로 보호 경로 쓰기", {"tool_name": "Bash",
           "tool_input": {"command": "echo hi > cases/sources/x.txt"}}, True)
    expect("훅 자신 수정", {"tool_name": "Edit",
           "tool_input": {"file_path": ".claude/hooks/protect_sources.py"}}, True)
    expect("settings.json 수정", {"tool_name": "Edit",
           "tool_input": {"file_path": ".claude/settings.json"}}, True)
    expect("baseline.json 수정", {"tool_name": "Edit",
           "tool_input": {"file_path": "baseline.json"}}, True)
    expect("samples/reference 수정", {"tool_name": "Write",
           "tool_input": {"file_path": "samples/reference/a.json"}}, True)

    # ↓ 아래 넷은 **한때 전부 빠져나갔다.** 다시 열리면 여기서 걸린다.
    expect("Windows 셸 명령도 Bash 도구로 전달", {"tool_name": "Bash",
           "tool_input": {"command": "Set-Content cases/sources/x.txt hi"}}, True)
    expect("셸로 baseline.json 지우기 (슬래시 없는 이름)", {"tool_name": "Bash",
           "tool_input": {"command": "rm baseline.json"}}, True)
    expect("보호 디렉터리를 통째로 지우기", {"tool_name": "Bash",
           "tool_input": {"command": "rm -rf cases/sources"}}, True)
    expect("보호 디렉터리를 통째로 (슬래시 없이)", {"tool_name": "Bash",
           "tool_input": {"command": "rm -rf .claude"}}, True)

    # ↓ 첫 토큰만 보면 빠져나간다. 쓰기 의도는 **모든 토큰**에서 본다.
    expect("cd 뒤에 오는 rm 도 잡는다", {"tool_name": "Bash",
           "tool_input": {"command": "cd nodes && rm -rf ../cases/sources"}}, True)


def passes() -> None:
    print("\n2. 통과해야 하는 것 — 오탐이 있으면 실습이 안 된다")
    expect("samples/work 쓰기", {"tool_name": "Write",
           "tool_input": {"file_path": "samples/work/a.json"}}, False)
    expect("cases/sources-old (다른 폴더)", {"tool_name": "Write",
           "tool_input": {"file_path": "cases/sources-old/a.txt"}}, False)
    expect("일반 코드 수정", {"tool_name": "Write",
           "tool_input": {"file_path": "nodes/draft.py"}}, False)
    # ↓ .claude/ 안에서도 명령·하위 에이전트 파일은 Claude 가 짓는 자리다 (7차시). 막으면 짓기가 안 된다.
    expect(".claude/commands 쓰기", {"tool_name": "Write",
           "tool_input": {"file_path": ".claude/commands/draft.md"}}, False)
    expect(".claude/agents 쓰기", {"tool_name": "Write",
           "tool_input": {"file_path": ".claude/agents/drafter.md"}}, False)
    expect("읽기", {"tool_name": "Read",
           "tool_input": {"file_path": "cases/sources/x.txt"}}, False)
    # 맨 이름을 보게 됐으니 **오탐 쪽도 같이 고정한다.**
    expect("baseline 이 단어로만 나오는 명령", {"tool_name": "Bash",
           "tool_input": {"command": "git commit -m baseline"}}, False)
    expect("보호 대상 아닌 폴더 지우기", {"tool_name": "Bash",
           "tool_input": {"command": "rm -rf runs"}}, False)

    # ↓ 읽기는 통과해야 한다. 2026-09-04 리뷰(N1): 슬래시만 보고 `cat` 까지 막았다.
    expect("cat 으로 보호 원문 읽기", {"tool_name": "Bash",
           "tool_input": {"command": "cat cases/sources/x"}}, False)
    expect("ls 로 보호 폴더 보기", {"tool_name": "Bash",
           "tool_input": {"command": "ls cases/sources/"}}, False)
    expect("cat 으로 settings.json 보기", {"tool_name": "Bash",
           "tool_input": {"command": "cat .claude/settings.json"}}, False)
    expect("git diff 로 표본 비교", {"tool_name": "Bash",
           "tool_input": {"command": "git diff samples/reference/a.json"}}, False)
    expect("훅 테스트 자체를 Bash 로 실행", {"tool_name": "Bash",
           "tool_input": {"command": "uv run python tests/test_hook.py"}}, False)
    expect("stderr 리다이렉션은 쓰기가 아니다", {"tool_name": "Bash",
           "tool_input": {"command": "cat cases/sources/x 2>/dev/null"}}, False)


def matcher_covers_tools() -> None:
    """`settings.json` 의 matcher 가 **스크립트가 처리하는 도구를 전부 부르는가.**

    스크립트가 처리하는 실제 Claude Code 도구와 matcher를 대조한다.
    """
    import re

    print()
    print("3. matcher 가 스크립트와 맞는가 — 배선이 빠지면 스크립트는 무의미하다")

    settings = load_settings()
    if settings is None:
        return
    # 원문 보호 장치를 부르는 등록만 본다(다른 장치 — 예: 모든 도구를 보는 guard — 는 따로 등록된다)
    entries = [e for e in settings["hooks"]["PreToolUse"]
               if any("protect_sources" in (h.get("command", "") + " ".join(h.get("args", []))) for h in e.get("hooks", []))]
    handled = sorted(HANDLED_TOOLS)

    for tool in handled:
        hit = any(re.search(e["matcher"], tool) for e in entries)
        if not hit:
            failures.append(f"matcher 가 {tool} 를 안 부른다")
        print(f"   {'OK  ' if hit else 'FAIL'}        {tool} 를 matcher 가 부른다")

    # 반대 방향 — 훅이 안 쓰는 도구까지 부르면 매 호출이 느려진다
    noise = [t for t in ("Read", "Glob", "Grep", "WebFetch")
             if any(re.search(e["matcher"], t) for e in entries)]
    ok = not noise
    if not ok:
        failures.append(f"matcher 가 쓸데없이 {noise} 까지 부른다")
    print(f"   {'OK  ' if ok else 'FAIL'}        읽기 전용 도구는 부르지 않는다")


def note(label: str, payload: dict) -> None:
    """판정에 넣지 않고 적기만 한다 — 막으면 더 잘 막는 것이고, 못 막으면 알려진 틈이다."""
    code = run(payload)
    print(f"   {'막음' if code == 2 else '통과'} exit={code}  (판정에 넣지 않음) | {label}")


def known_gaps() -> None:
    """**못 막는 것.** 이건 결함이 아니라 이 훅의 범위다. 더 잘 막는 장치가 떨어지지 않게 판정에서 뺀다."""
    print("\n4. **알려진 틈** — 못 막는다는 것을 잊지 않으려고 적어 둔다 (막아도, 못 막아도 판정은 그대로)")
    note("⚠️ cd 로 경로를 바꾸면 못 잡을 수 있다", {"tool_name": "Bash",
         "tool_input": {"command": "cd cases && echo hi > sources/x.txt"}})
    # ⚠️ 이건 **막힌다.** 테스트를 쓰면서 못 막을 거라 예상했는데 틀렸다 —
    #    경로 조각에 `cases/sources` 가 그대로 보이기 때문이다.
    #    **추측으로 한계를 적지 않는다. 돌려 보고 적는다.**
    expect("상대 경로여도 조각이 보이면 잡는다", {"tool_name": "Bash",
           "tool_input": {"command": "cd nodes && echo hi > ../cases/sources/x.txt"}}, True)
    note("⚠️ 리다이렉션 없는 쓰기 (python -c ...)", {"tool_name": "Bash",
         "tool_input": {"command": "python -c \"open('x','w')\""}})
    note("⚠️ 경로가 없는 입력", {"tool_name": "Write"})


REQUIRE_INTERPRETER = "--require-interpreter" in sys.argv


def load_settings() -> dict | None:
    """등록 파일을 읽는다. 아직 없으면(장치를 먼저 짓고 등록은 맨 마지막에 한다) FAIL 한 줄로 적고 None."""
    path = ROOT / ".claude" / "settings.json"
    if not path.is_file():
        check(".claude/settings.json 이 있다 (등록은 맨 마지막에 만든다 — 그 전에는 이 줄만 FAIL)", False)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        check(f".claude/settings.json 을 JSON 으로 읽는다 — {e}", False)
        return None


def check(label: str, cond: bool) -> None:
    if not cond:
        failures.append(label)
    print(f"   {'OK  ' if cond else 'FAIL'}        {label}")


def stderr_is_utf8() -> None:
    """차단 메시지가 **UTF-8 로** 나가는가. Windows 의 cp949 파이프를 흉내 낸다.

    2026-09-04 Windows live smoke: 보호는 됐는데 Claude Code 화면의 한글이 깨졌다.
    앞 절들은 PYTHONUTF8=1 을 넘겨서 이 결함을 못 봤다. 여기서는 일부러 cp949 를 강제한다.
    """
    print()
    print("6. 차단 메시지 인코딩 — Windows 파이프(cp949)에서도 UTF-8 인가")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8",)}
    env["PYTHONIOENCODING"] = "cp949"
    proc = subprocess.run([sys.executable, str(HOOK)],
                          input=json.dumps({"tool_name": "Write",
                                            "tool_input": {"file_path": PROTECTED_DIR_SAMPLE + "/x"}}).encode("utf-8"),
                          capture_output=True, env=env)
    try:
        text = proc.stderr.decode("utf-8")
        # 이유 문장은 사람마다 다르다 — 막았고(2), 이유가 비어 있지 않고, 한글이 온전한지만 본다
        good = proc.returncode == 2 and any("가" <= ch <= "힣" for ch in text)
    except UnicodeDecodeError:
        good = False
    check("stderr 가 UTF-8 이고 한글이 온전하다 (cp949 강제 환경에서)", good)


def settings_wiring() -> None:
    """settings.json 이 선언한 **그대로** 스폰해 본다.

    앞 섹션들은 스크립트를 직접 불렀다. 그래서 settings.json 의 `command`·`args` 가
    틀려도 전부 통과했다 — 2026-09-04 리뷰(B1)가 실제 세션에서 잡았다.
    exec form(`args`)은 셸을 거치지 않아 `$CLAUDE_PROJECT_DIR` 가 풀리지 않고,
    Claude Code 는 `${CLAUDE_PROJECT_DIR}` 만 치환한다. 그 상태의 훅은 python 이
    파일을 못 열어 exit 2 → **모든 도구 호출이 막힌다.** WSL 처럼 `python` 이 없으면
    아무 표시 없이 그냥 안 돈다.
    """
    import shutil

    print()
    print("5. settings 배선 — 선언한 대로 스폰되는가")
    settings = load_settings()
    if settings is None:
        return
    entries = [h for e in settings.get("hooks", {}).get("PreToolUse", []) for h in e.get("hooks", [])
               if "protect_sources" in (h.get("command", "") + " ".join(h.get("args", [])))]
    if not entries:
        check("PreToolUse 에 원문 보호 장치 등록이 있다", False)
        return
    hook_decl = entries[0]
    command = str(hook_decl.get("command", ""))
    args = [str(a) for a in (hook_decl.get("args") or [])]
    project = ROOT

    bare = [a for a in args if "$CLAUDE_PROJECT_DIR" in a and "${CLAUDE_PROJECT_DIR}" not in a]
    check("플레이스홀더가 ${CLAUDE_PROJECT_DIR} 형태다 (중괄호 없으면 안 풀린다)", not bare)
    check("args 가 이 훅 스크립트를 가리킨다", any(a.endswith("protect_sources.py") for a in args))

    exe = shutil.which(command)
    if exe is None:
        msg = f"차단 장치가 부르는 `{command}` 이 PATH 에 없다 — uv 를 설치하고 터미널을 새로 연다"
        if REQUIRE_INTERPRETER:
            failures.append(msg)
            print(f"   FAIL        {msg}")
        else:
            print(f"   MISS        {msg}. 이 기계에서는 배선을 스폰해 보지 못했다")
        return

    resolved = [a.replace("${CLAUDE_PROJECT_DIR}", str(project)) for a in args]

    def spawn(payload: dict) -> int:
        proc = subprocess.run(
            [exe, *resolved], input=json.dumps(payload), text=True,
            encoding="utf-8", errors="replace", capture_output=True,
            env={**os.environ, "PYTHONUTF8": "1", "CLAUDE_PROJECT_DIR": str(project)},
        )
        return proc.returncode

    protected_dir = PROTECTED_DIR_SAMPLE
    check(f"선언한 argv 로 {protected_dir}/x Write → 2 (차단)",
          spawn({"tool_name": "Write",
                 "tool_input": {"file_path": str(project / protected_dir / "x")}}) == 2)
    check("선언한 argv 로 samples/work/x Write → 0 (통과)",
          spawn({"tool_name": "Write",
                 "tool_input": {"file_path": str(project / "samples" / "work" / "x")}}) == 0)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")

    blocks()
    passes()
    matcher_covers_tools()
    known_gaps()
    stderr_is_utf8()
    settings_wiring()

    print()
    if failures:
        print(f"실패 {len(failures)}건")
        for line in failures:
            print(f"   {line}")
        return 1
    print("훅이 **가드레일 범위 안에서** 동작한다.")
    print()
    print("⚠️ 4번을 보라. **경계가 아니다.**")
    print("   진짜 경계가 필요하면 보호 대상을 에이전트 작업공간 밖에 두고")
    print("   CI 가 해시로 대조해야 한다. 이 훅은 거기까지 하지 않는다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
