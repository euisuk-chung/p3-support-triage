"""R3 — 근거가 **문의 본문에 그대로 있나.**

블로그의 인용 검사(G3)와 같은 논리를 다른 일에 쓴 것이다.

    블로그  quote 가 자료 원문에 있나
    문의    evidence 가 문의 본문에 있나

**형태가 검증을 싸게 만든다.** 근거를 요약하게 두면 대조할 방법이 없다.

## 정규화 범위

연속 공백과 줄바꿈을 단일 공백으로 접는다. **대소문자는 유지한다.**
블로그와 같은 규칙이다 — 규칙이 프로젝트마다 다르면 학생이 헷갈린다.

## ⚠️ 근거가 본문에 있다고 판단이 맞는 건 아니다

*"결제가 두 번 됐어요"* 를 근거로 `account` 라고 해도 이 검사는 통과한다.
**근거의 존재와 추론의 타당성은 다르다.** 그건 정답표(오프라인)나 사람이 본다.
"""

from __future__ import annotations

import re

from . import GuardResult


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check(data: dict, case) -> GuardResult:
    items = data.get("classifications", [])
    if not items:
        return GuardResult("R3", "evidence_grounded", 0.0, False, ["분류가 없다"])

    bodies = {t.id: normalize(t.text) for t in case.tickets()}
    bad = []
    for item in items:
        tid = item["ticket_id"]
        body = bodies.get(tid)
        if body is None:
            continue                      # R2 가 잡는다
        if normalize(item["evidence"]) not in body:
            bad.append(f"{tid}: 본문에 없는 근거 — '{item['evidence'][:60]}'")

    checked = [i for i in items if i["ticket_id"] in bodies]
    score = (len(checked) - len(bad)) / len(checked) if checked else 0.0
    return GuardResult("R3", "evidence_grounded", score, not bad, bad)
