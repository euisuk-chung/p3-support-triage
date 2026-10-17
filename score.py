"""정확도를 잰다. **오프라인 전용이다 — 운영 게이트가 아니다.**

    uv run python score.py --case case-01-mixed              한 케이스
    uv run python score.py                                   전부, 표로
    uv run python score.py --fail-on-regression              어제보다 나빠졌으면 1

## 흐름(`review.py`·`scripts/deliver.py`)과 무엇이 다른가

    review.py · deliver.py   이 문의들을 내보내도 되나 · 어디로 보낼까   `Case` 만 받는다.  정답 필요 없음
    score.py                 **분류가 정답과 맞았나**                  `EvalSpec` 을 읽는다. 정답 필요함

**구조로 갈렸다.** `Case` 에는 정답표가 없고 `EvalSpec` 에만 있다.
흐름은 `EvalSpec` 을 받지 않는다 — 관례가 아니라 경계다.

운영에는 정답표가 없다. 새로 들어온 문의가 무슨 카테고리인지 미리 아는 사람이 없다.
**그래서 정확도는 발행 게이트가 될 수 없다.**

> 블로그의 G4(커버리지)를 두고도 같은 정리를 했다.
> 온라인 게이트와 오프라인 평가는 **같은 코드를 써도 하는 일이 다르다.**

## 게이트가 둘이다 — 블로그와 같은 규약

    임계값 게이트   score.py --case X              정확도가 기준을 넘나
    회귀 게이트     score.py --fail-on-regression  어제보다 나빠졌나
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

from _utf8 import force_utf8  # noqa: E402
from case import Case, find_cases, load_eval  # noqa: E402
from scoring import escalation_report, score  # noqa: E402

BASELINE = ROOT / "baseline.json"


def load_output(case: Case) -> list[dict]:
    """표본 결과물을 읽는다. 실제 실행 한 번의 draft.json 을 저장해 둔 것이다."""
    path = ROOT / "samples" / "reference" / f"{case.name}.json"
    if not path.exists():
        raise SystemExit(f"표본이 없다: samples/reference/{path.name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["classifications"]


def report_one(path: Path) -> dict:
    """**여기서만** 정답표를 읽는다. 흐름은 `load_eval` 을 부르지 않는다."""
    case = Case.load(path)
    spec = load_eval(path)                     # ← 오프라인 전용
    items = load_output(case)
    s = score(items, spec.labels)
    esc = escalation_report(items, case.confidence_threshold, spec.expect_escalated)
    return {
        "case": case.name,
        "accuracy": s.accuracy,
        "threshold": spec.accuracy_threshold,
        "passed": s.passes(spec.accuracy_threshold),
        "notes": s.notes(),
        "escalation": esc,
    }


def gate(name: str) -> int:
    paths = [p for p in find_cases(ROOT / "cases") if p.stem == name]
    if not paths:
        raise SystemExit(f"그런 케이스가 없다: {name}")
    r = report_one(paths[0])

    acc = "잴 수 없음" if r["accuracy"] is None else f"{r['accuracy']:.2f}"
    print(f"{r['case']}: 정확도 {acc} "
          f"(기준 {r['threshold']:.2f}) → {'통과' if r['passed'] else '거부'}")
    for line in r["notes"]:
        print(f"   {line}")
    esc = r["escalation"]
    if esc["missed"]:
        print(f"   ⚠️ **사람이 봐야 하는데 자동으로 나갔다**: {', '.join(esc['missed'])}")
    if esc["over"]:
        print(f"   사람 큐로 과하게 넘겼다: {', '.join(esc['over'])}")
    print(f"   사람 큐 비율 {esc['rate']:.2f}")
    return 0 if r["passed"] else 1


def report(save_baseline: bool, fail_on_regression: bool) -> int:
    paths = find_cases(ROOT / "cases")
    if not paths:
        raise SystemExit("케이스를 찾지 못했다")

    # ⚠️ 케이스의 `expect` 를 여기 넣지 않는다. 그건 **흐름의 판정**이고
    #    여기는 **정확도**다. 섞으면 이 파일이 경계하자는 혼동을 이 파일이 만든다.
    #    흐름이 기대대로 판정하는지는 `test_checks.py` 가 본다.
    print(f"{'케이스':<26} {'정확도':>7} {'기준':>6} {'사람큐':>7}  판정")
    print("-" * 62)
    accuracy = {}
    notes = []
    for path in paths:
        r = report_one(path)
        case_name = r["case"]
        if r["accuracy"] is not None:
            accuracy[case_name] = r["accuracy"]
        mark = "통과" if r["passed"] else "거부"
        shown = "  n/a" if r["accuracy"] is None else f"{r['accuracy']:7.2f}"
        print(f"{case_name:<26} {shown} {r['threshold']:>6.2f} "
              f"{r['escalation']['rate']:>7.2f}  {mark}")
        for line in r["notes"]:
            notes.append(f"   {case_name}  {line}")
        if r["escalation"]["missed"]:
            notes.append(f"   {case_name}  ⚠️ 자동으로 나갔다: "
                         f"{', '.join(r['escalation']['missed'])}")

    if notes:
        print()
        for line in notes:
            print(line)

    print()
    print("⚠️ **정확도는 오프라인 지표다.** 운영에는 정답표가 없어 이 게이트를 걸 수 없다.")
    print("   그리고 정확도가 높아도 운영 검사(review.py)가 거부할 수 있다 —")
    print("   `case-02-unknown-category` 가 그렇다. 정답과는 맞는데 **카테고리 계약을 어겼다.**")
    print("   그 판정은 `test_checks.py` 가 본다. 두 질문을 한 표에 섞지 않는다.")

    if save_baseline:
        BASELINE.write_text(
            json.dumps({"schema_version": 1, "accuracy": accuracy}, indent=2) + "\n",
            encoding="utf-8")
        print(f"\n기준 저장: {len(accuracy)}개 케이스")
        return 0

    previous = load_baseline()
    dropped = []
    if previous:
        dropped = [f"{n} {previous[n]:.2f} → {v:.2f}"
                   for n, v in accuracy.items() if n in previous and v < previous[n]]
        added = [n for n in accuracy if n not in previous]
        print()
        if dropped:
            print("정확도가 기준보다 떨어진 케이스")
            for line in dropped:
                print(f"   {line}")
        else:
            print("정확도 하락 없음")
        if added:
            print(f"   새 케이스 (비교 대상 아님): {', '.join(added)}")
    elif fail_on_regression:
        print("\n⚠️ 기준이 없다. --save-baseline 을 먼저 한 번 돌린다.")
        return 1

    if fail_on_regression and dropped:
        print(f"\n회귀 게이트: 하락 {len(dropped)}건 — 거부")
        return 1
    return 0


def load_baseline() -> dict[str, float]:
    if not BASELINE.exists():
        return {}
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    scores = data.get("accuracy")
    return scores if isinstance(scores, dict) else {}


def main() -> int:
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="케이스 하나를 임계값 게이트로 판정한다")
    parser.add_argument("--save-baseline", action="store_true")
    parser.add_argument("--fail-on-regression", action="store_true",
                        help="기준보다 떨어진 케이스가 있으면 종료 코드 1")
    args = parser.parse_args()

    if args.case:
        return gate(args.case)
    return report(args.save_baseline, args.fail_on_regression)


if __name__ == "__main__":
    sys.exit(main())
