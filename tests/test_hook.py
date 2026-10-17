"""훅이 **무엇을 막고 무엇을 못 막는가.**

    uv run python tests/test_hook.py

## 블로그의 같은 파일과 구조는 같고 **보호 대상이 다르다**

여기서 지키는 것은 셋이다.

    cases/tickets   문의 원문. 고칠 수 있으면 근거 검사(R3)가 무의미해진다
    baseline.json   회귀 기준. 낮추면 하락이 사라진다 — score.py --fail-on-regression
    assignments/    라우팅 결과(티켓당 파일 하나). 손으로 고치면 무엇이 자동인지 흐려진다

⚠️ `baseline.json` 은 **한동안 보호 대상이 아니었다.** 블로그에는 있고 여기엔 빠져 있었다.
같은 파일이 같은 이유로 위험한데 한쪽만 지키고 있었다. 이 테스트가 그걸 고정한다.

## 알려진 통과를 고정한다

이 훅은 **경계가 아니라 가드레일**이다. 못 막는 것을 실행 가능한 테스트로 박아 둔다.
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


def _protected_dirs() -> list[str]:
    import importlib.util
    spec = importlib.util.spec_from_file_location("hook", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.PROTECTED_DIRS)


PROTECTED_DIR_SAMPLE = _protected_dirs()


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
    expect("Write cases/tickets/", {"tool_name": "Write",
           "tool_input": {"file_path": "cases/tickets/2026-08-31.json"}}, True)
    expect("NotebookEdit (notebook_path)", {"tool_name": "NotebookEdit",
           "tool_input": {"notebook_path": "cases/tickets/x.ipynb"}}, True)
    expect("Bash 로 문의 원문 쓰기", {"tool_name": "Bash",
           "tool_input": {"command": "echo hi > cases/tickets/x.json"}}, True)
    expect("훅 자신 수정", {"tool_name": "Edit",
           "tool_input": {"file_path": ".claude/hooks/protect_sources.py"}}, True)
    expect("settings.json 수정", {"tool_name": "Edit",
           "tool_input": {"file_path": ".claude/settings.json"}}, True)
    expect("samples/reference 수정", {"tool_name": "Write",
           "tool_input": {"file_path": "samples/reference/a.json"}}, True)

    # ↓ 아래 다섯은 **한때 전부 빠져나갔다.** 다시 열리면 여기서 걸린다.
    expect("**baseline.json 수정** — 블로그엔 있고 여기엔 빠져 있었다", {"tool_name": "Edit",
           "tool_input": {"file_path": "baseline.json"}}, True)
    expect("셸로 baseline.json 지우기 (슬래시 없는 이름)", {"tool_name": "Bash",
           "tool_input": {"command": "rm baseline.json"}}, True)
    expect("Windows 셸 명령도 Bash 도구로 전달", {"tool_name": "Bash",
           "tool_input": {"command": "Set-Content cases/tickets/x.json hi"}}, True)
    expect("assignments/ 를 통째로 지우기", {"tool_name": "Bash",
           "tool_input": {"command": "rm -rf assignments/"}}, True)
    expect("cases/tickets 를 통째로 지우기", {"tool_name": "Bash",
           "tool_input": {"command": "rm -rf cases/tickets"}}, True)

    # ↓ 첫 토큰만 보면 빠져나간다. 쓰기 의도는 **모든 토큰**에서 본다.
    expect("cd 뒤에 오는 rm 도 잡는다", {"tool_name": "Bash",
           "tool_input": {"command": "cd nodes && rm -rf ../cases/tickets"}}, True)


def passes() -> None:
    print("\n2. 통과해야 하는 것 — 오탐이 있으면 실습이 안 된다")
    expect("samples/work 쓰기", {"tool_name": "Write",
           "tool_input": {"file_path": "samples/work/a.json"}}, False)
    expect("cases/tickets-old (다른 폴더)", {"tool_name": "Write",
           "tool_input": {"file_path": "cases/tickets-old/a.json"}}, False)
    expect("일반 코드 수정", {"tool_name": "Write",
           "tool_input": {"file_path": "nodes/classify.py"}}, False)
    expect("읽기", {"tool_name": "Read",
           "tool_input": {"file_path": "cases/tickets/x.json"}}, False)
    expect("baseline 이 단어로만 나오는 명령", {"tool_name": "Bash",
           "tool_input": {"command": "git commit -m baseline"}}, False)
    expect("보호 대상 아닌 폴더 지우기", {"tool_name": "Bash",
           "tool_input": {"command": "rm -rf runs"}}, False)
    expect("채점기 실행 (기준을 읽기만 한다)", {"tool_name": "Bash",
           "tool_input": {"command": "python score.py --fail-on-regression"}}, False)

    # ↓ 읽기는 통과해야 한다. 2026-09-04 리뷰(N1): 슬래시만 보고 `cat` 까지 막았다.
    expect("cat 으로 보호 원문 읽기", {"tool_name": "Bash",
           "tool_input": {"command": "cat cases/tickets/x"}}, False)
    expect("ls 로 보호 폴더 보기", {"tool_name": "Bash",
           "tool_input": {"command": "ls cases/tickets/"}}, False)
    expect("cat 으로 settings.json 보기", {"tool_name": "Bash",
           "tool_input": {"command": "cat .claude/settings.json"}}, False)
    expect("git diff 로 표본 비교", {"tool_name": "Bash",
           "tool_input": {"command": "git diff samples/reference/a.json"}}, False)
    expect("훅 테스트 자체를 Bash 로 실행", {"tool_name": "Bash",
           "tool_input": {"command": "python tests/test_hook.py"}}, False)
    expect("stderr 리다이렉션은 쓰기가 아니다", {"tool_name": "Bash",
           "tool_input": {"command": "cat cases/tickets/x 2>/dev/null"}}, False)


def matcher_covers_tools() -> None:
    """`settings.json` 의 matcher 가 **스크립트가 처리하는 도구를 전부 부르는가.**

    스크립트가 처리하는 실제 Claude Code 도구와 matcher를 대조한다.
    """
    import importlib.util
    import re

    print()
    print("3. matcher 가 스크립트와 맞는가 — 배선이 빠지면 스크립트는 무의미하다")

    spec = importlib.util.spec_from_file_location("hook", HOOK)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)

    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    # 원문 보호 장치를 부르는 등록만 본다(다른 장치 — 예: 모든 도구를 보는 guard — 는 따로 등록된다)
    entries = [e for e in settings["hooks"]["PreToolUse"]
               if any("protect_sources" in (h.get("command", "") + " ".join(h.get("args", []))) for h in e.get("hooks", []))]
    handled = sorted(hook.WRITERS | hook.SHELL_TOOLS)

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


def known_gaps() -> None:
    """**못 막는 것.** 이건 결함이 아니라 이 훅의 범위다."""
    print("\n4. **알려진 통과** — 못 막는다는 것을 잊지 않으려고 박아 둔다")
    expect("⚠️ cd 로 경로를 바꾸면 못 잡는다", {"tool_name": "Bash",
           "tool_input": {"command": "cd cases && echo hi > tickets/x.json"}}, False)
    expect("상대 경로여도 조각이 보이면 잡는다", {"tool_name": "Bash",
           "tool_input": {"command": "cd nodes && echo hi > ../cases/tickets/x.json"}}, True)
    expect("⚠️ 리다이렉션 없는 쓰기 (tee, python -c ...)", {"tool_name": "Bash",
           "tool_input": {"command": "python -c \"open('x','w')\""}}, False)
    expect("⚠️ 읽을 수 없는 입력이면 막지 않는다 (fail-open)", {"tool_name": "Write"}, False)
    # ⚠️ 정답표는 cases/*.yaml 의 labels 다. 파일 하나가 아니라 **필드**라서
    #    경로 단위로 보는 이 훅으로는 "케이스는 고치되 답만 못 고치게" 할 수 없다.
    expect("⚠️ 케이스 파일 자체는 막지 않는다 (정답표가 그 안에 있다)",
           {"tool_name": "Write", "tool_input": {"file_path": "cases/case-01-mixed.yaml"}}, False)


REQUIRE_INTERPRETER = "--require-interpreter" in sys.argv


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
                                            "tool_input": {"file_path": next(iter(PROTECTED_DIR_SAMPLE)) + "/x"}}).encode("utf-8"),
                          capture_output=True, env=env)
    try:
        text = proc.stderr.decode("utf-8")
        good = proc.returncode == 2 and "고칠 수 없다" in text
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
    import importlib.util
    import shutil

    print()
    print("5. settings 배선 — 선언한 대로 스폰되는가")
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hook_decl = settings["hooks"]["PreToolUse"][0]["hooks"][0]
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

    spec = importlib.util.spec_from_file_location("hook", HOOK)
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    protected_dir = next(iter(hook.PROTECTED_DIRS))
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
    print("   특히 정답표(cases/*.yaml 의 labels)는 경로로 못 가른다.")
    print("   그건 사람이 리뷰하거나 오프라인 정답표를 따로 두어야 한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
