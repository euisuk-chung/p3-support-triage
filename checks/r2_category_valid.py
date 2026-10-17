"""R2 — **정해진 카테고리인가**, 그리고 문의와 1:1 인가.

## 이게 이 프로젝트에서 가장 싼 검사다

카테고리 목록은 사람이 적어 둔다. 그러면 판정이 **집합 포함**으로 끝난다.
정답이 필요 없다 — *"이 목록 안인가"* 는 운영에서도 물을 수 있다.

> **출력을 닫힌 집합으로 만들면 검사가 공짜가 된다.**
> 자유 텍스트로 받으면 이 검사가 불가능하다. 형태가 검증 비용을 정한다.

## 세 가지를 잡는다

    목록 밖    "환불요청" 같은 걸 지어냈다
    빠뜨림     문의는 넷인데 분류가 셋
    더함       없는 티켓 id 를 만들었다
"""

from __future__ import annotations

from . import GuardResult


def check(data: dict, case) -> GuardResult:
    items = data.get("classifications", [])
    allowed = set(case.categories)
    expected = {t.id for t in case.tickets()}
    actual = {c["ticket_id"] for c in items}

    detail = []
    unknown = sorted({c["category"] for c in items} - allowed)
    if unknown:
        detail.append(f"**목록에 없는 카테고리**: {', '.join(unknown)} "
                      f"(쓸 수 있는 것: {', '.join(sorted(allowed))})")

    missed = sorted(expected - actual)
    if missed:
        detail.append(f"분류하지 않은 문의: {', '.join(missed)}")

    invented = sorted(actual - expected)
    if invented:
        detail.append(f"**없는 문의 id 를 만들었다**: {', '.join(invented)}")

    dupes = sorted({tid for tid in actual if
                    sum(1 for c in items if c["ticket_id"] == tid) > 1})
    if dupes:
        detail.append(f"같은 문의를 두 번 분류했다: {', '.join(dupes)}")

    good = sum(1 for c in items
               if c["category"] in allowed and c["ticket_id"] in expected)
    total = max(len(items), len(expected)) or 1
    return GuardResult("R2", "category_valid", good / total, not detail, detail)
