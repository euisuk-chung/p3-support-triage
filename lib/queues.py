"""문의를 담당에게 넘긴다. **여기가 이 프로젝트의 외부 효과다.**

## 정본은 **티켓 하나에 파일 하나**다 — 큐별 파일이 아니다

> ⚠️ **2026-08-31 재설계.** 초판은 큐마다 JSON 하나를 두고 그 안에 티켓을 담았다.
> 리뷰가 잡았다 — **큐를 바꾸면 이전 큐에서 안 지워져 한 티켓이 두 군데에 남았다.**
> "담당은 하나" 라고 문서에 적어 놓고 코드가 안 지켰다.
>
> read-modify-write 라 죽으면 파일이 깨지고, 깨진 파일을 `{}` 로 숨겨서
> **다음 쓰기가 큐 전체를 지울** 수도 있었다.

지금은 이렇게 둔다.

    assignments/<티켓 해시>.json   ← **현재 담당. 이게 정본이다**

큐별 목록은 여기서 **파생**한다. 정본이 하나면 "두 곳에 남는" 일이 생길 수 없다.

## 알림과 결정적으로 다르다 — **덮어쓰기라 자연히 멱등이다**

| | 효과의 모양 | 두 번 하면 |
|---|---|---|
| 알림 발송 | **붙이기**(append) | **두 번 간다.** 되돌릴 수 없다 |
| 담당 지정 | **덮어쓰기**(upsert) | 같은 상태로 수렴한다 |

그래서 **문의 분류에는 알림의 번호표(`idempotency.py`)가 필요 없다.** 필요한 것은
번호표 원장이 아니라 **현재 담당의 원자적 upsert** 다.

> 멱등성은 트리거 종류가 아니라 **효과의 의미**에서 온다.

## ⚠️ 이 범위를 넘으면 다시 설계해야 한다

    지금의 효과 = 티켓 담당 upsert **하나**
    알림·자동 답변·외부 시스템 enqueue 는 **범위 밖이다**

담당을 지정하면서 **알림을 함께 보내면** 알림의 문제가 그대로 돌아온다.
그때는 담당 지정과 알림 보내기를 다른 단계로 가르고 멱등성 결정을 다시 해야 한다.

**효과 하나를 보고 "멱등이다" 라고 하면 안 된다. 묶음 전체를 봐야 한다.**
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Assignment:
    ticket_id: str
    queue: str
    at: str
    fields: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"ticket_id": self.ticket_id, "queue": self.queue,
                "at": self.at, **self.fields}


class Assignments:
    """현재 담당. **티켓 하나에 파일 하나.**"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, ticket_id: str) -> Path:
        # 티켓 id 를 그대로 파일 이름으로 쓰지 않는다. 무엇이 들어올지 모른다.
        digest = hashlib.sha256(ticket_id.encode("utf-8")).hexdigest()[:32]
        return self.root / f"{digest}.json"

    # ---------- 쓰기 ----------

    def assign(self, ticket_id: str, queue: str, *, at: str | None = None,
               **fields: Any) -> Assignment:
        """담당을 정한다. **덮어쓴다.**

        같은 값을 다시 넣으면 파일 내용도 같다 — `at` 을 밖에서 받는 이유다.
        시각을 안에서 만들면 같은 지정을 재적용해도 **파일이 달라져** "수렴한다" 가
        말뿐이 된다. 재실행이 같은 상태로 수렴하는지 시험할 수 있어야 한다.
        """
        record = Assignment(ticket_id, queue, at or _now(), dict(fields))
        _atomic_write(self._path(ticket_id), record.to_dict())
        return record

    # ---------- 읽기 ----------

    def of(self, ticket_id: str) -> Assignment | None:
        return self._read(self._path(ticket_id))

    @staticmethod
    def _read(path: Path) -> Assignment | None:
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return None
        known = {"ticket_id", "queue", "at"}
        if not known <= set(raw):
            return None
        return Assignment(raw["ticket_id"], raw["queue"], raw["at"],
                          {k: v for k, v in raw.items() if k not in known})

    def all(self) -> list[Assignment]:
        return [a for p in sorted(self.root.glob("*.json")) if (a := self._read(p))]

    def corrupt(self) -> list[Path]:
        """읽을 수 없는 기록. **숨기지 않는다.**

        초판은 깨진 파일을 `{}` 로 읽어서, 다음 쓰기가 큐 전체를 지울 수 있었다.
        """
        return [p for p in sorted(self.root.glob("*.json")) if self._read(p) is None]

    # ---------- 파생 ----------

    def queue(self, name: str) -> list[Assignment]:
        """큐별 목록. **정본에서 파생한다.**"""
        return [a for a in self.all() if a.queue == name]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for a in self.all():
            out[a.queue] = out.get(a.queue, 0) + 1
        return out

    def where(self, ticket_id: str) -> str | None:
        """이 티켓의 **현재** 담당. 정본이 하나라 답도 하나다."""
        found = self.of(ticket_id)
        return found.queue if found else None


def _atomic_write(path: Path, payload: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".assign-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
