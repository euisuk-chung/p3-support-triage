"""R1 — 형식이 계약을 지켰나. 깨지면 나머지를 볼 것도 없다."""

from __future__ import annotations

import json
from pathlib import Path

from . import GuardResult

SCHEMA = Path(__file__).resolve().parents[1] / "schema.json"


def check(data: dict, case) -> GuardResult:
    try:
        import jsonschema
    except ImportError:
        # 검증기가 없는 것은 **내용 실패가 아니라 실행 환경 문제**다. 거부로 조용히 넘기지 않는다.
        raise SystemExit("jsonschema 가 설치되지 않았다. R1 을 실행할 수 없다.\n"
                         "  uv sync   (이 저장소 맨 위)")

    try:
        jsonschema.validate(data, json.loads(SCHEMA.read_text(encoding="utf-8")))
    except jsonschema.ValidationError as exc:
        where = "/".join(str(p) for p in exc.absolute_path) or "(최상위)"
        return GuardResult("R1", "schema_valid", False, False, [f"{where}: {exc.message}"])
    return GuardResult("R1", "schema_valid", True, True)
