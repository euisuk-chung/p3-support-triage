"""검사 케이스 — 문의와 정답표를 읽는다.

**블로그·알림의 `case.py` 와 또 다르다.** 셋을 비교해 보면 무엇이 공유되고
무엇이 안 되는지가 한눈에 보인다.

    블로그  sources · required               자료와 빠지면 안 될 항목
    알림    quotes · conditions              시세와 조건
    문의    tickets · categories · labels    문의와 카테고리와 **정답표**

## 운영이 보는 것과 채점이 보는 것을 **구조로** 가른다

> ⚠️ 초판은 `labels` 를 `Case` 안에 두고 흐름에 그대로 넘겼다.
> 단계가 안 읽었을 뿐이지 **읽을 수는 있었다.** 그건 관례이지 경계가 아니다.

    Case       문의 · 카테고리 · 확신 임계값        → `Case.load()` · `request_case()` — 흐름이 받는다
    EvalSpec   **정답표** · 정확도 임계값 · 기대 판정 → `load_eval()` — 오프라인(score.py·시험)만

**파일은 하나여도 읽는 객체가 둘이다.** `Case` 에는 `labels` 필드 자체가 없어서,
수집·검수·전달이 실수로든 고의로든 정답표에 닿을 수 없다.
drafter 는 더 멀다 — 요청 폴더에 복사된 문의(`tickets.json`)만 받는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Ticket:
    id: str
    subject: str
    body: str

    @property
    def text(self) -> str:
        """근거 대조에 쓰는 원문. 제목과 본문을 합친다."""
        return f"{self.subject}\n{self.body}"


@dataclass
class EvalSpec:
    """**오프라인 전용.** 정답표와 기대 판정.

    ⚠️ 흐름은 이 객체를 **받지 못한다.** `Case.load()`·`request_case()` 가 `Case` 만 돌려주고,
    `EvalSpec` 은 `load_eval()` 로 따로 읽는다. `score.py` 와 테스트만 부른다.

    > 단계가 **안 읽는 것**과 **못 읽는 것**은 다르다.
    > 초판은 `Case.eval` 로 들고 다녀서 단계가 읽을 수 있었다 — 관례였지 경계가 아니었다.
    """

    labels: dict[str, str] = field(default_factory=dict)
    accuracy_threshold: float = 0.75
    expect: str = "routed"                     # graph.yaml 의 terminal 이름과 같은 어휘
    expect_escalated: list[str] = field(default_factory=list)


@dataclass
class Case:
    """**운영이 보는 것만** 담는다.

    문의·카테고리·확신 임계값. **정답표는 여기 없다.**
    """

    name: str
    root: Path
    tickets_path: str = ""
    categories: list[str] = field(default_factory=list)
    confidence_threshold: float = 0.8
    _loaded: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Case:
        raw = _read(path)
        categories = list(raw.get("categories") or [])
        if not categories:
            raise ValueError(f"{path.name}: categories 가 비었다. 무엇으로 분류할지 정해야 한다")
        return cls(
            name=path.stem,
            root=path.parent,
            tickets_path=raw.get("tickets") or "",
            categories=categories,
            confidence_threshold=float(raw.get("confidence_threshold", 0.8)),
        )

    # ---------- 문의 ----------

    def loaded(self) -> dict[str, Any]:
        if not self._loaded:
            path = self.root / self.tickets_path
            if not path.is_file():
                raise FileNotFoundError(f"문의 파일이 없다: {path}")
            self._loaded = json.loads(path.read_text(encoding="utf-8"))
        return self._loaded

    def tickets(self) -> list[Ticket]:
        return [Ticket(t["id"], t["subject"], t["body"])
                for t in self.loaded().get("tickets", [])]

    def ticket(self, tid: str) -> Ticket | None:
        return next((t for t in self.tickets() if t.id == tid), None)

    @property
    def received_date(self) -> str:
        return self.loaded().get("received_date", "")


def _read(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_eval(path: Path) -> EvalSpec:
    """**오프라인 쪽만 부른다.** 같은 YAML 에서 정답표 부분을 읽는다.

    파일은 하나여도 **읽는 객체가 둘**이면 경계가 선다.
    흐름(collect·review·deliver)은 `Case.load()`·`request_case()` 만 쓰고 이 함수를 부르지 않는다.
    """
    raw = _read(path)
    return EvalSpec(
        labels=dict(raw.get("labels") or {}),
        accuracy_threshold=float(raw.get("accuracy_threshold", 0.75)),
        expect=(raw.get("expect") or "routed").strip(),
        expect_escalated=list(raw.get("expect_escalated") or []),
    )


ROOT = Path(__file__).resolve().parents[1]


def request_case(req: Path) -> Case:
    """요청 폴더 하나의 `Case` — 검수(review.py)와 전달(deliver.py)이 같은 것을 보게.

    문의는 수집(collect.py)이 요청 폴더에 복사해 둔 `tickets.json` 을 읽는다 — drafter 가 본 것과 같은 것.
    카테고리·확신 임계값은 케이스로 연 연습 요청이면 그 케이스 파일에서,
    inbox 로 들어온 문의면 policies.yaml 의 `triage:` 칸에서 읽는다. **정답표는 어디서도 읽지 않는다.**
    """
    state = json.loads((req / "state.json").read_text(encoding="utf-8"))
    name = state.get("case")
    if name:
        base = Case.load(ROOT / "cases" / f"{name}.yaml")
        categories, threshold = base.categories, base.confidence_threshold
    else:
        pol = _read(ROOT / "policies.yaml").get("triage") or {}
        categories = list(pol.get("categories") or [])
        threshold = float(pol.get("confidence_threshold", 0.8))
        if not categories:
            raise ValueError("policies.yaml 의 triage.categories 가 비었다. 무엇으로 분류할지 정해야 한다")
    return Case(name=req.name, root=req, tickets_path="tickets.json",
                categories=categories, confidence_threshold=threshold)


def find_cases(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(directory.glob("case-*.yaml"))
