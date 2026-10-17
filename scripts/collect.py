"""수집 — 도착한 문의를 요청 폴더로 모은다. 모델을 부르지 않는다.

    uv run python scripts/collect.py <요청 id>

문의가 어디서 오나
  inbox 로 들어온 요청   state.json 의 source(예: inbox/T-1041.json)
  연습 요청(--case)      케이스(cases/*.yaml)가 가리키는 문의 파일
실무라면 여기가 티켓 시스템 API 다. 바뀌는 것은 이 스크립트 하나이고, 뒤의 작성·검수·전달은 그대로다.

만드는 것
  requests/<id>/tickets.json   문의 사본 — id·제목·본문·받은 날짜만. drafter 와 검수가 **같은 것**을 본다
  requests/<id>/brief.json     쓸 수 있는 카테고리 · 분류할 문의 id · 쓸 곳 · 형식

넣지 않는 것 — 정답표(labels)와 확신 기준선. 정답표는 운영에 없고(score.py 만 본다),
기준선을 보여 주면 모델이 확신을 기준선에 맞춰 적을 수 있다.
문의가 없거나, 받은 날짜가 없거나, 파일을 읽을 수 없으면 64(실행 환경 문제)로 끝난다.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from case import Case, request_case  # noqa: E402


def source_path(state: dict) -> Path:
    if state.get("case"):
        case = Case.load(ROOT / "cases" / f"{state['case']}.yaml")
        return case.root / case.tickets_path
    src = Path(state.get("source") or "")
    return src if src.is_absolute() else ROOT / src


def main() -> int:
    rid = sys.argv[1]
    d = ROOT / "requests" / rid
    state = json.loads((d / "state.json").read_text(encoding="utf-8"))
    src = source_path(state)
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"collect: 문의 파일을 읽을 수 없다: {src.name} ({type(e).__name__})")
        return 64
    tickets = [{"id": t["id"], "subject": t.get("subject", ""), "body": t.get("body", "")}
               for t in raw.get("tickets") or [] if isinstance(t, dict) and t.get("id")]
    if not tickets:
        print("collect: 문의가 하나도 없다")
        return 64
    if not raw.get("received_date"):
        # 담당 기록의 시각을 여기서 받는다 — 전달이 시계를 읽지 않아야 다시 실행해도 같은 파일이 나온다
        print("collect: 받은 날짜(received_date)가 없다")
        return 64
    (d / "tickets.json").write_text(json.dumps({"received_date": raw["received_date"], "tickets": tickets},
                                               ensure_ascii=False, indent=2), encoding="utf-8")
    case = request_case(d)
    brief = {
        "categories": case.categories,
        "tickets": [t["id"] for t in tickets],
        "write_to": f"requests/{rid}/draft.json",
        "format": {"classifications": [{"ticket_id": "문의 id 그대로", "category": "categories 가운데 하나",
                                        "confidence": "0~1 — 애매하면 낮게",
                                        "evidence": "문의 제목·본문에 그대로 있는 구절"}]},
    }
    (d / "brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"collect: 문의 {len(tickets)}건, 카테고리 {len(case.categories)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
