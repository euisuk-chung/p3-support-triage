# 프로젝트 3 — 고객 문의 분류 (완성 코드)

도착한 고객 문의를 담당 팀 큐에 나누고, AI 의 확신이 낮은 것은 사람 큐로 보내는 자동화의 완성 코드입니다. 블로그 자동화와 같은 뼈대(요청 → 수집 → 작성 → 검수 → 전달)로 되어 있고, 문의는 지어낸 연습 자료입니다.

## 어디에 두나

이 저장소는 혼자 쓰지 않고, 15차시 첫머리에 내 실습 저장소 맨 위에서 `triage` 폴더로 받아 씁니다.

```bash
git clone https://github.com/euisuk-chung/harness-p3-support-triage.git triage
```

내 저장소의 `.gitignore` 가 `triage/` 를 빼 두어서, 받은 코드는 내 저장소에 저장되지 않습니다. 이 폴더에는 제 `pyproject.toml` 이 있어서, 여기서 처음 `uv run` 을 치면 폴더 안에 제 `.venv` 가 생깁니다.

## 이 저장소의 지도

| 역할 | 파일 |
|---|---|
| Claude 를 부르는 곳 | `scripts/request.sh` — `claude -p "/handle-request <요청 id>"` 를 부르는 곳은 여기 한 곳 |
| 시작 계기 | `scripts/cron.example` — 매분 `scripts/watch.sh` 가 `inbox/` 를 보고 문의 파일마다 `scripts/request.sh` |
| 지시 | `CLAUDE.md`(프로젝트 지침) · `.claude/commands/handle-request.md`(본 세션) · `.claude/agents/drafter.md`(작성 담당, 이 업무의 규칙) · `.claude/skills/drafter-rules/SKILL.md`(늘 같은 규칙) · `graph.yaml` 의 `ask`·`retry_hint`(다시 쓰라는 글) |
| 차단 장치 | `.claude/hooks/` — 등록은 `.claude/settings.json` |
| 막는 규칙 | `policies.yaml` · `.claude/settings.json` 의 `permissions.deny` |
| 흐름 단계 (모델 없음) | `scripts/open_request.py` · `scripts/collect.py` · `review.py` 와 `checks/` · `scripts/deliver.py` |
| 사람이 치는 것 | `score.py`(정답표 채점 — 흐름 밖) · `review.py`(검사) |
| 업무 모듈 | `lib/` — 케이스 읽기 `case.py` · 큐 `queues.py` · 채점 계산 `scoring.py` |
| 시험 | `tests/` |
| 입력 견본 | `cases/` |

## 해 보기

`triage` 폴더에서 모델을 부르지 않고:

```bash
uv run python score.py --case case-01-mixed
uv run python tests/test_checks.py
```

값을 바꿔 보는 실습은 폴더를 통째로 복사한 사본(`triage-copy`)에서 합니다. 업무 말과 파일 이름의 대응은 [`CLAUDE.md`](./CLAUDE.md) 의 "이 프로젝트의 선언" 표에 있습니다.
