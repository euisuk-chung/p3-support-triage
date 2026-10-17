# 문의 분류 — 도착한 고객 문의를 담당 팀 큐에, 애매한 것은 사람 큐에

이 폴더에서 대화 창을 연다: `cd triage` 뒤 `claude --add-dir ..`(모델은 3차시에 `/model` 로 저장해 둔 본 에이전트 모델) (한 층 위 PRD.md 를 읽으려고 `--add-dir ..`).
Claude Code 는 연 폴더의 `.claude/` 만 읽는다 — 다른 폴더에서 열면 아래 장치가 걸리지 않는다.

## 이 프로젝트의 선언

| 업무 말 | 이름 | 이 프로젝트에서 |
|---|---|---|
| 요청 | `request` | 문의 파일이 `inbox/` 에 생기면 — cron 이 매분 `scripts/watch.sh` 로 확인해 파일마다 `scripts/request.sh <파일>`. 요청 id 는 문의 한 건이면 `issue-<티켓 id>`(예: `issue-T-1041`), 묶음이면 `batch-<내용 지문>`. 같은 문의가 다시 오면 `skip`. 연습은 `scripts/request.sh --case <케이스>` 로 `<케이스>-<번호>` |
| 수집 | `collect` | `scripts/collect.py` — 문의를 요청 폴더(`tickets.json`)로, 카테고리 목록을 `brief.json` 으로. 정답표·기준선은 넣지 않는다. 모델 없음 |
| 작성 | `draft` | 하위 에이전트 `drafter`(`.claude/agents/drafter.md`, 도구 Read·Write) 가 `requests/<id>/draft.json` 에 문의마다 카테고리·확신·근거를 쓴다 |
| 검수 | `review` | `review.py --request <id>` — 검사 셋 R1~R3(형식·카테고리 유효성·근거가 문의에 그대로 있나). 정답표를 쓰지 않는다. 모델 없음 |
| 승인 | `approve` | 따로 단계가 없다 — 확신이 기준선(0.8) 아래인 문의만 사람 큐(`human-review`)로 가서 사람이 정한다. 전달이 가른다 |
| 전달 | `deliver` | `scripts/deliver.py <id>` — 팀 큐·사람 큐에 넣기(`lib/queues.py`, 덮어쓰기라 두 번 해도 같다). 차단 장치가 실행하고 Claude 에게는 이 도구가 없다 |

- 명령: `/handle-request <요청 id>`(요청 하나를 끝까지)
- 차단 장치(`.claude/settings.json`): `protect_sources.py`(문의 원문·기준·담당 기록 보호) · `guard.py`(막기 — `policies.yaml`) · `run_review.py`(분류가 쓰이면 검수) · `next_step.py`(멈추려 할 때 다음 단계 — `graph.yaml`) · `show_status.py`(새 세션에 진행표)
- 흐름도 `graph.yaml` · 정책 `policies.yaml`(허용 도구·쓸 곳·명령, 그리고 inbox 문의에 쓰는 카테고리·기준선·팀 큐)
- 끝 상태: `routed`(전부 팀 큐, 신호 0) · `escalated`(일부가 사람 큐 — 정상, 신호 3) · `needs_human`(작성 세 번에도 검수 거부, 신호 3) · `failed`(신호 1)
- 오프라인 채점은 흐름 밖: `score.py`(정답표로 정확도·사람 큐 비율·놓침·과잉) · 검사기 시험 `tests/test_checks.py`

## 지킬 것

- 분류는 drafter 만 쓴다. 본 세션은 진행만 맡고, 큐에 넣지 않는다(`scripts/deliver.py` 를 부르지 않는다).
- `cases/`·`inbox/`·요청 폴더의 `tickets.json` 은 문의 원문이라 고치지 않는다. `assignments/` 는 전달만 쓴다.
- 정답표(`cases/*.yaml` 의 `labels`)는 `score.py`·`tests/test_checks.py` 만 읽는다. 흐름(수집·작성·검수·전달)에 넘기지 않는다.
- `state.json`·`events.jsonl`·`STATUS.md` 는 차단 장치가 쓴다. 고치지 않는다.
