"""검수 — 이 분류를 큐에 넣어도 되는지 검사 셋(R1~R3)으로 판정한다. 모델을 부르지 않는다. **정답표를 쓰지 않는다.**

    uv run python review.py --request case-01-mixed-1    요청 폴더의 분류(requests/<id>/draft.json)를 검수. 흐름이 부른다
    uv run python review.py --case case-01-mixed         저장된 답(samples/)을 검수. 종료 코드가 곧 판정
    uv run python review.py                              보고서. 전부 보여만 준다

운영에서도 그대로 도는 검사만 여기 둔다. 정확도는 정답표가 있어야 재니 `score.py` 로 갔다.

    review.py --case X   이 분류를 큐에 넣어도 되나       (운영 검사 — 정답 필요 없음)
    score.py --case X    분류가 정답과 맞았나             (오프라인 채점 — 정답표 필요)
    test_checks.py       검사기가 제대로 잡나              (검사기 시험)

## 종료 코드

    --request   0 통과 · 1 거부(작성으로 되돌아간다) · 2 draft.json 을 읽을 수 없다 · 64 요청 폴더가 이상하다
    --case      0 통과 · 1 거부
    (없음)      보고서라 늘 0 — 일부러 거부되게 만든 케이스(case-02)가 섞여 있다
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
from case import Case, find_cases, request_case  # noqa: E402
from checks import GuardResult, r1_schema, r2_category_valid, r3_evidence_grounded, verdict  # noqa: E402

CHECKS = [r1_schema, r2_category_valid, r3_evidence_grounded]

# 거부됐을 때 drafter 에게 넘길 고치는 법 — 검사마다 하나
HOW = {
    "schema_valid": "출력 형식이 계약과 다르다. schema.json 을 정확히 지켜라.",
    "category_valid": "주어진 카테고리 목록 안에서만 고르고, 문의마다 하나씩 낸다.",
    "evidence_grounded": "근거를 **문의 원문에서 그대로** 옮겨라. 요약하지 마라.",
}


def run_checks(data: dict, case: Case) -> list[GuardResult]:
    results = []
    for check in CHECKS:
        r = check.check(data, case)
        results.append(r)
        if r.guard == "R1" and not r.passed:
            break  # 형식이 깨졌으면 나머지는 볼 것도 없다
    return results


def load_sample(case: Case) -> dict:
    path = ROOT / "samples" / "reference" / f"{case.name}.json"
    if not path.exists():
        raise SystemExit(f"표본 결과물이 없다: samples/reference/{path.name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("_note", None)
    return data


def gate(name: str) -> int:
    paths = [p for p in find_cases(ROOT / "cases") if p.stem == name]
    if not paths:
        raise SystemExit(f"그런 케이스가 없다: {name}")
    case = Case.load(paths[0])
    results = run_checks(load_sample(case), case)
    ok = verdict(results)
    print(f"{case.name}: {'큐에 넣어도 됨' if ok else '거부'}  (운영 검사 R1~R3)")
    for r in results:
        for line in r.detail:
            print(f"   {case.name}  {r.guard}  {line}")
    return 0 if ok else 1


def report() -> int:
    for path in find_cases(ROOT / "cases"):
        case = Case.load(path)
        results = run_checks(load_sample(case), case)
        cells = " · ".join(f"{r.guard} {r.format_metric()}" for r in results)
        print(f"{case.name:<26} {cells}  {'통과' if verdict(results) else '거부'}")
    print("\n이 표는 보고서다. 거부가 섞여 있는 것이 정상이다 — 일부러 거부되게 만든 케이스가 있다.")
    print("검사기가 옳게 도는지는 test_checks.py 가 판정한다.")
    return 0


def review_request(rid: str) -> int:
    """요청 폴더의 분류를 검수한다. 문의는 수집이 복사해 둔 tickets.json — drafter 가 본 것과 같다."""
    d = ROOT / "requests" / rid
    try:
        data = json.loads((d / "draft.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("객체가 아니다")
    except (OSError, ValueError, TypeError) as e:
        print(f"review: 형식 위반 — draft.json 을 읽을 수 없다 ({type(e).__name__})")
        return 2
    try:
        case = request_case(d)
    except (OSError, ValueError, KeyError) as e:
        print(f"review: 요청 폴더를 읽을 수 없다 ({type(e).__name__}: {e})")
        return 64
    results = run_checks(data, case)
    (d / "review.json").write_text(json.dumps(
        {r.guard: {"pass": r.passed, "detail": r.detail} for r in results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(" · ".join(f"{r.guard} {'pass' if r.passed else 'rejected'}" for r in results))
    bad = [r for r in results if not r.passed]
    for r in bad:
        for line in r.detail or ["거부"]:
            print(f"review: {r.guard} rejected — {line}")
    for r in bad:
        print(f"review: {r.guard} 고치는 법 — {HOW.get(r.metric_name, '기준에 못 미친다')}")
    return 1 if bad else 0


def main() -> int:
    force_utf8()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--request", help="요청 폴더의 분류를 검수한다(흐름이 부른다)")
    parser.add_argument("--case", help="케이스 하나의 저장된 답을 검수한다")
    args = parser.parse_args()
    if args.request:
        return review_request(args.request)
    if args.case:
        return gate(args.case)
    return report()


if __name__ == "__main__":
    sys.exit(main())
