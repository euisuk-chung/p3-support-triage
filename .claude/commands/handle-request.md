---
description: 요청 하나(도착한 문의 묶음)를 끝까지 처리한다 — 수집·작성·검수·전달(큐에 넣기) (15차시)
argument-hint: <요청 id, 예: issue-T-1041>
allowed-tools: Read, Agent, Task, Bash(uv run python scripts/open_request.py:*)
---

## 요청을 연 결과

!`uv run python scripts/open_request.py $ARGUMENTS`

## 할 일

당신은 이 요청의 진행을 맡습니다. 분류를 직접 쓰지 않고, 큐에 넣지 않습니다.

1. 위 결과가 "작성" 을 요구하면, 하위 에이전트 **drafter** 에게 맡깁니다. 백그라운드로 띄우지 말고 끝날 때까지 기다립니다. 요청 id 와 쓸 곳을 그대로 넘기고, 검수가 거부한 이유가 적혀 있으면 그 줄들도 그대로 넘깁니다.
2. drafter 가 끝나면 멈춥니다. 검수와 큐에 넣기(확신이 낮은 것은 사람 큐)는 차단 장치가 합니다.
3. 멈추려 할 때 차단 장치가 다시 작성하라고 하면, drafter 를 **다시 불러** 그 안내를 그대로 넘깁니다. 기다리기 예약이나 다른 도구로 시간을 보내지 않습니다.
4. 그 밖의 일은 하지 않습니다.
