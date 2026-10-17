"""요청 열기·마무리 — 모델을 부르지 않는다.

    uv run python scripts/open_request.py --event inbox/T-1041.json     문의 파일 하나가 도착(같은 문의는 한 번만)
    uv run python scripts/open_request.py --case case-01-mixed          연습 요청(열 때마다 새 번호)
    uv run python scripts/open_request.py <요청 id>                      이미 연 요청의 지금 안내
    uv run python scripts/open_request.py --finish <요청 id>             claude 가 끝난 뒤 마무리
    uv run python scripts/open_request.py --id-for inbox/T-1041.json    그 파일이 열 요청 id 만 찍는다(열지 않는다)

문의 파일이 열 요청의 id 는 내용에서 나온다 — 시각이나 파일 이름이 아니다.
  문의가 한 건이면   issue-<티켓 id>          ("T-1041 이 열렸다" 는 사건은 하나뿐이다 — issue:T-1041:opened)
  여러 건 묶음이면   batch-<내용 지문 12자>    (같은 묶음이 다시 배달되면 같은 id)
요청 폴더를 먼저 만드는(mkdir) 쪽 하나만 이긴다. 이미 끝난 요청이면 Claude 를 부르지 않고 건너뛴다.

끝날 때 신호
  열기     0 작성이 필요하다(claude 를 부른다) · 10 이미 처리한 문의(건너뜀) · 64 파일·케이스가 없다
  마무리   0 routed · 3 escalated(일부가 사람 큐 — 정상) 또는 needs_human · 1 failed
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
from _state import REQ, advance, event, load, rdir, save, utf8  # noqa: E402

SKIP = 10


def new_state(rid: str, case: str | None, source: str | None, trigger: str) -> dict:
    return {"id": rid, "case": case, "source": source, "trigger": trigger, "at": "collect", "visits": {},
            "history": [], "tool_calls": 0, "terminal": None, "reason": ""}


def start(rid: str, case: str | None, source: str | None, trigger: str) -> int:
    save(rid, new_state(rid, case, source, trigger))
    event(rid, "triggered", trigger=trigger, case=case, source=source)
    (REQ / ".current").write_text(rid, encoding="utf-8")
    print(trigger)
    r = advance(rid, "open")
    print(r["message"])
    print(f"REQUEST_ID={rid}")
    return 0 if r["need"] else finish_code(load(rid))


def event_id(path: Path) -> tuple[str, str]:
    """문의 파일 → (요청 id, 사건 이름). 내용으로 정한다 — 같은 문의가 두 번 배달돼도 같은 id."""
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    tickets = data.get("tickets") or []
    if len(tickets) == 1:
        tid = str(tickets[0].get("id", ""))
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", tid)[:40]   # 티켓 id 를 그대로 폴더 이름으로 쓰지 않는다
        return f"issue-{safe}", f"issue:{tid}:opened"
    digest = hashlib.sha256(raw).hexdigest()[:12]
    return f"batch-{digest}", f"batch:{digest}:opened ({len(tickets)}건)"


def open_event(file: str) -> int:
    path = (ROOT / file) if not Path(file).is_absolute() else Path(file)
    if not path.is_file():
        print(f"그런 문의 파일이 없다: {file}")
        return 64
    try:
        rid, name = event_id(path)
    except (ValueError, UnicodeDecodeError) as e:
        print(f"문의 파일을 읽을 수 없다: {file} ({type(e).__name__})")
        return 64
    REQ.mkdir(exist_ok=True)
    try:
        rdir(rid).mkdir()                      # 먼저 만드는 쪽 하나만 이긴다
    except FileExistsError:
        st = load(rid)
        if st.get("terminal"):
            print(f"skip: already processed {rid} ({st['terminal']})")
            return SKIP
        print(f"resume: {rid} 은 {st.get('at')} 단계에서 멈춰 있다")
        return reopen(rid)
    rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    return start(rid, None, rel, f"event:{name} ← {rel}")


def open_practice(case: str) -> int:
    if not (ROOT / "cases" / f"{case}.yaml").is_file():
        print(f"그런 케이스가 없다: {case}")
        return 64
    REQ.mkdir(exist_ok=True)
    n = 1
    while True:
        rid = f"{case}-{n}"
        try:
            rdir(rid).mkdir()
            break
        except FileExistsError:
            n += 1
    return start(rid, case, None, f"manual:{case}")


def reopen(rid: str) -> int:
    if not load(rid):
        print(f"그런 요청이 없다: {rid}")
        return 64
    (REQ / ".current").write_text(rid, encoding="utf-8")
    r = advance(rid, "open")
    print(r["message"])
    print(f"REQUEST_ID={rid}")
    return 0 if r["need"] else finish_code(load(rid))


def finish_code(st: dict) -> int:
    return {"routed": 0, "escalated": 3, "needs_human": 3}.get(st.get("terminal"), 1)


def path_lines(st: dict) -> list[str]:
    """지나온 길을 화면 줄로. 검수가 거부한 뒤 다시 작성한 것은 retry n/m 으로 적는다."""
    hist = st.get("history", [])
    out, first, retry, cap, i = [], [], 0, 3, 0
    while i < len(hist) and not (hist[i]["step"] == "review" and hist[i]["signal"] != 0):
        first.append(hist[i]["step"])
        i += 1
    if i >= len(hist):
        out.append(" → ".join(first + [st.get("terminal") or "?"]))
    else:
        first.append("review")
        out.append(" → ".join(first))
        out.append(f"review: {hist[i]['note'].replace('review: ', '')}")
        i += 1
        while i < len(hist):
            h = hist[i]
            if h["step"] == "draft":
                retry += 1
                nxt = hist[i + 1] if i + 1 < len(hist) else None
                tail = ""
                if nxt and nxt["step"] == "review":
                    tail = " → review: " + ("pass" if nxt["signal"] == 0 else nxt["note"].replace("review: ", ""))
                    i += 1
                out.append(f"draft (retry {retry}/{cap - 1}){tail}")
            else:
                out.append(h["step"])
            i += 1
    # 끝 줄 — 이유가 있으면 이유, 큐에 넣었으면 전달이 남긴 요약(팀 큐·사람 큐 건수)
    why = st.get("reason") or next((h.get("note", "") for h in reversed(hist) if h["step"] == "deliver"), "")
    out.append(f"done: {st.get('terminal')}" + (f" — {why}" if why else ""))
    return out


def finish(rid: str) -> int:
    st = load(rid)
    if not st:
        print(f"그런 요청이 없다: {rid}")
        return 1
    if not st.get("terminal"):
        advance(rid, "finish")
        st = load(rid)
    lines = path_lines(st)
    q = rdir(rid) / "queues.json"
    if q.is_file():                      # 전달이 남긴 큐 나눔 — 끝 줄 앞에
        qs = json.loads(q.read_text(encoding="utf-8"))
        lines[-1:-1] = [f"  팀 큐   {len(qs['team'])}건: {', '.join(qs['team']) or '-'}",
                        f"  사람 큐 {len(qs['human'])}건: {', '.join(qs['human']) or '-'}"
                        f"  (기준선 {qs['threshold']:.2f} 아래)"]
    for line in lines:
        print(line)
    cur = REQ / ".current"
    if cur.is_file() and cur.read_text(encoding="utf-8").strip() == rid:
        cur.unlink()
    return finish_code(st)


def main() -> int:
    utf8()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rid", nargs="?", help="이미 연 요청 id")
    p.add_argument("--event", metavar="문의_파일", help="inbox/ 에 도착한 문의 파일")
    p.add_argument("--case", help="케이스 이름으로 연습 요청을 연다")
    p.add_argument("--finish", metavar="요청_ID", help="claude 가 끝난 뒤 마무리")
    p.add_argument("--id-for", metavar="문의_파일", help="그 파일이 열 요청 id 만 찍는다")
    a = p.parse_args()
    if a.id_for:
        try:
            print(event_id(Path(a.id_for))[0])
            return 0
        except (OSError, ValueError, UnicodeDecodeError) as e:
            print(f"문의 파일을 읽을 수 없다: {a.id_for} ({type(e).__name__})")
            return 64
    if a.finish:
        return finish(a.finish)
    if a.event:
        return open_event(a.event)
    if a.case:
        return open_practice(a.case)
    if a.rid:
        return reopen(a.rid)
    p.print_help()
    return 64


if __name__ == "__main__":
    sys.exit(main())
