"""전달 — 검수를 통과한 분류를 큐에 넣는다. 모델을 부르지 않는다. **여기가 이 프로젝트의 외부 효과다.**

    uv run python scripts/deliver.py <요청 id>
    uv run python scripts/deliver.py <요청 id> --root <폴더>     requests/·assignments/ 가 다른 곳에 있을 때(시험용)

확신으로 갈린다. **둘 다 정상이다.**

    확신 >= 기준선   →  팀 큐로(policies.yaml 의 teams)
    확신 <  기준선   →  **사람 큐로**(human-review) — 이 프로젝트의 승인. 사람이 카드를 보고 정한다

기준선은 연습 요청이면 케이스 파일, inbox 로 들어온 문의면 policies.yaml 의 값이다(case.request_case).

## 사람 큐로 가는 것은 실패가 아니다

이걸 실패로 치면 기준선을 낮추게 되고, 결국 애매한 것도 자동으로 나간다.
**"애매하면 사람에게" 가 설계다.** 다만 공짜가 아니다 — 넘기는 비율이 높으면 사람이 감당 못 하고
결국 대충 승인하게 된다. 그 비율은 score.py 가 오프라인에서 잰다.

## 다시 실행해도 된다 — 덮어쓰기라서

담당은 **티켓 하나에 파일 하나**(queues.py)라, 같은 지정을 다시 해도, 다른 큐로 옮겨도 담당은 언제나 하나다.
중간에 죽었으면 이 스크립트를 **처음부터 다시** 돌리면 된다 — 앞서 넣은 것을 같은 값으로 다시 넣을 뿐이다.
시각을 시계에서 읽지 않고 문의의 받은 날짜에서 받는 것도 그래서다. 시계를 읽으면 다시 돌릴 때마다
파일이 달라져 "같은 상태로 수렴한다" 가 말뿐이 된다. test_checks.py 5번이 중간에 죽이고 다시 돌려 확인한다.

끝날 때 신호: 0 전부 팀 큐(routed) · 3 일부가 사람 큐(escalated — 정상) · 64 읽을 파일이 없다
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from case import request_case  # noqa: E402
from queues import Assignments  # noqa: E402

HUMAN = "human-review"
TEAM = {"billing": "billing-team", "account": "account-team", "bug": "engineering", "howto": "support-l1"}


def teams() -> dict[str, str]:
    import yaml
    pol = yaml.safe_load((ROOT / "policies.yaml").read_text(encoding="utf-8")) or {}
    return (pol.get("triage") or {}).get("teams") or TEAM


def deliver(req: Path, store: Assignments) -> tuple[list[str], list[tuple[str, float]], float]:
    """요청 폴더 하나의 분류를 큐에 넣는다. (팀 큐로 간 id, 사람 큐로 간 (id, 확신), 기준선)"""
    case = request_case(req)
    items = json.loads((req / "draft.json").read_text(encoding="utf-8")).get("classifications", [])
    received = json.loads((req / "tickets.json").read_text(encoding="utf-8"))["received_date"]
    at = f"{received}T00:00:00Z"          # 다시 실행해도 같은 파일이 나오게 — 시계를 읽지 않는다
    threshold = case.confidence_threshold
    team = teams()
    routed, escalated = [], []
    for item in items:
        tid, category = item["ticket_id"], item["category"]
        confidence = float(item.get("confidence", 0))
        if confidence < threshold:
            # 사람이 처음부터 다시 읽지 않게, 모델의 제안과 넘긴 이유를 같이 남긴다
            store.assign(tid, HUMAN, at=at, proposed=category, confidence=confidence,
                         why=f"확신 {confidence:.2f} < 임계 {threshold:.2f}")
            escalated.append((tid, confidence))
        else:
            store.assign(tid, team.get(category, "support-l1"), at=at, category=category, confidence=confidence)
            routed.append(tid)
    return routed, escalated, threshold


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rid")
    ap.add_argument("--root", default=str(ROOT), help="requests/ 와 assignments/ 가 있는 폴더")
    a = ap.parse_args()
    base = Path(a.root)
    req = base / "requests" / a.rid
    if not (req / "draft.json").is_file() or not (req / "tickets.json").is_file():
        print(f"deliver: requests/{a.rid}/ 에 draft.json 또는 tickets.json 이 없다")
        return 64
    routed, escalated, threshold = deliver(req, Assignments(base / "assignments"))
    total = len(routed) + len(escalated)
    (req / "queues.json").write_text(json.dumps(
        {"threshold": threshold, "team": routed, "human": [t for t, _ in escalated]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    if routed:
        print(f"팀 큐로 {len(routed)}건: {', '.join(routed)}")
    if escalated:
        print(f"사람 큐로 {len(escalated)}건: " + ", ".join(f"{t} (확신 {c:.2f} < 임계 {threshold:.2f})"
                                                   for t, c in escalated))
    print(f"사람 큐 비율 {len(escalated)}/{total}")
    if escalated:
        print(f"팀 큐 {len(routed)}건 · 사람 큐 {len(escalated)}건({', '.join(t for t, _ in escalated)}). "
              "일부가 사람 큐로 갔다. 실패가 아니다 — 확신이 낮으면 사람이 본다.")
        return 3
    print(f"팀 큐 {len(routed)}건 · 사람 큐 0건. 전부 담당 팀으로 갔다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
