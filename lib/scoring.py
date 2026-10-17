"""정답표와 대조한다. **오프라인 전용이다.**

## 온라인과 오프라인이 갈리는 자리

이 프로젝트가 블로그·알림보다 이걸 선명하게 보여 준다.

| | 무엇을 보나 | 정답이 필요한가 | 언제 실행하나 |
|---|---|---|---|
| `checks/` R1~R3 | 형식·카테고리 유효성·근거 | **필요 없다** | **운영에서도** |
| `scoring.py` | **정확도** | **필요하다** | 케이스에서만 |

운영에는 정답이 없다. 새로 들어온 문의가 무슨 카테고리인지 미리 아는 사람이 없다.
**그래서 정확도는 운영 게이트가 될 수 없다.**

## ⚠️ 정답 집합을 기준으로 센다 — 초판은 반대였고, 그게 틀렸다

> **2026-08-31 수정.** 초판은 **예측을 순회**하며 라벨이 있는 것만 셌다.
> 그래서 **넷 중 셋만 내고 셋을 맞히면 정확도 1.00** 이 됐다.
> 리뷰가 재현했다 — `accuracy=1.0 total=3`.
>
> 빠뜨린 것이 분모에서 사라지면 **아무것도 안 내는 게 만점**이 된다.

지금은 **라벨을 순회**한다. 예측이 없으면 `missing` 이고, 그것도 틀린 것이다.

    맞힘      정답과 같은 예측이 있다
    틀림      예측이 있는데 다르다
    누락      예측이 아예 없다          ← 초판이 세지 않던 것
    중복      같은 티켓을 두 번 예측했다  ← 초판이 세지 않던 것
    라벨 없음  예측은 있는데 정답이 없다   ← 별도로 본다. 분모에 안 넣는다

## 정답이 있으면 검사가 싸진다 — 그게 전부는 아니다

분류는 정답표를 적어 두면 정확도가 공짜로 나온다. 블로그의 인용 검사보다 훨씬 싸다.

**그런데 정답표를 만드는 일이 사람 몫이다.** 공짜인 것은 대조이지 라벨링이 아니다.
라벨이 틀리면 정확도가 거짓말을 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Score:
    """정답표 대조 결과. **분모는 라벨 개수다.**"""

    total: int = 0                              # 라벨이 있는 티켓 수
    correct: int = 0
    wrong: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)      # 라벨은 있는데 예측이 없다
    duplicated: list[str] = field(default_factory=list)   # 같은 티켓을 두 번 예측했다
    extra: list[str] = field(default_factory=list)        # 예측은 있는데 라벨이 없다

    @property
    def accuracy(self) -> float | None:
        """라벨이 하나도 없으면 **`None`** 이다. `0.0` 이 아니다.

        "잴 수 없다" 와 "0점" 은 다르다. 0.0 으로 두면 임계값 게이트가
        **아무 예측도 없는 케이스를 거부**하는 것처럼 보인다.
        """
        return self.correct / self.total if self.total else None

    @property
    def clean(self) -> bool:
        """중복·라벨 없는 예측이 없는가. **정확도와 별개 축이다.**"""
        return not (self.duplicated or self.extra)

    def passes(self, threshold: float) -> bool:
        acc = self.accuracy
        return acc is not None and acc >= threshold and self.clean

    def notes(self) -> list[str]:
        out = [f"틀림 {w['ticket_id']}: 정답 {w['want']} · 답 {w['got']}" for w in self.wrong]
        if self.missing:
            out.append(f"**예측 누락**: {', '.join(self.missing)} — 이것도 틀린 것으로 센다")
        if self.duplicated:
            out.append(f"**중복 예측**: {', '.join(self.duplicated)}")
        if self.extra:
            out.append(f"라벨 없는 예측: {', '.join(self.extra)} (분모에 넣지 않는다)")
        return out


def score(classifications: list[dict], labels: dict[str, str]) -> Score:
    """분류와 정답표를 맞춰 본다. **라벨을 기준으로 센다.**"""
    result = Score()

    # 같은 티켓을 두 번 예측했는지 먼저 본다. 뒤엣것으로 덮어쓰면 중복이 숨는다.
    seen: dict[str, dict] = {}
    for item in classifications:
        tid = item["ticket_id"]
        if tid in seen:
            if tid not in result.duplicated:
                result.duplicated.append(tid)
            continue          # 첫 예측을 쓴다. 어느 쪽을 쓰든 중복은 이미 오류다
        seen[tid] = item

    for tid, want in labels.items():
        result.total += 1
        item = seen.get(tid)
        if item is None:
            # ⚠️ 여기가 초판에 없던 줄이다. 분모에는 넣고 정답에는 안 넣는다.
            result.missing.append(tid)
            continue
        if item["category"] == want:
            result.correct += 1
        else:
            result.wrong.append(
                {"ticket_id": tid, "want": want, "got": item["category"],
                 "confidence": item.get("confidence")})

    result.extra = sorted(set(seen) - set(labels))
    return result


def escalation_report(classifications: list[dict], threshold: float,
                      expect_escalated: list[str]) -> dict:
    """확신도 임계값이 **의도한 대로 갈리는가.**

    두 가지를 본다.

        놓침   사람이 봐야 할 것이 자동으로 나갔다  ← 위험하다
        과잉   자동으로 돼도 될 것이 사람 큐로 갔다  ← 사람 큐가 병목이 된다

    둘 다 문제다. *"애매하면 사람에게"* 는 공짜가 아니다 —
    넘기는 비율이 높으면 사람이 감당 못 하고 결국 대충 승인하게 된다.
    """
    low = {c["ticket_id"] for c in classifications if c.get("confidence", 0) < threshold}
    want = set(expect_escalated)
    return {
        "escalated": sorted(low),
        "missed": sorted(want - low),          # 넘어갔어야 하는데 자동으로 나갔다
        "over": sorted(low - want),            # 안 넘겨도 되는데 넘겼다
        "rate": len(low) / len(classifications) if classifications else 0.0,
    }
