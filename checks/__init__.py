"""이 프로젝트의 검사. **정답표를 쓰지 않는다.**

    R1  schema_valid       형식이 계약을 지켰나
    R2  category_valid     **정해진 카테고리인가** + 문의와 1:1 인가
    R3  evidence_grounded  근거가 본문에 그대로 있나

## 왜 정확도가 여기 없나

정확도는 **정답표가 있어야** 잰다. 운영에는 정답이 없다.
`checks/` 는 운영에서도 도는 것만 둔다 — 정확도는 `scoring.py` 로 갔다.

> 섞으면 *"운영에서도 정확도를 재고 있다"* 는 착각이 생긴다.

## 블로그·알림과 하나도 안 겹친다

    블로그  G1~G5   출처·인용·누락·의견비율
    알림    C1~C4   카테고리 없음. 값 정확·전망 금지
    문의    R1~R3   **카테고리 유효성**·근거

겹치는 것은 `GuardResult` 형식과 "지표 하나에 검사 하나" 뿐이다.
그 형식은 아래에 이 폴더만의 사본으로 둔다 — 한 프로젝트 폴더만 떼어 가도 돌게.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GuardResult:
    """검사 하나의 결과.

    metric  지표 값 (bool 또는 0.0~1.0)
    passed  기준을 통과했는가
    detail  실패했을 때 어디를 고칠지 — 문의 번호와 이유
    """

    guard: str            # R1 … R3
    metric_name: str      # schema_valid, category_valid …
    metric: Any
    passed: bool
    detail: list[str] = field(default_factory=list)

    def format_metric(self) -> str:
        if isinstance(self.metric, bool):
            return "ok" if self.metric else "fail"
        if isinstance(self.metric, (int, float)):
            return f"{self.metric:.2f}"
        return str(self.metric)


def verdict(results: list[GuardResult]) -> bool:
    """전부 통과해야 통과다. 하나라도 거부면 거부다."""
    return all(r.passed for r in results)


from . import r1_schema, r2_category_valid, r3_evidence_grounded  # noqa: E402

__all__ = ["GuardResult", "verdict", "r1_schema", "r2_category_valid", "r3_evidence_grounded"]
