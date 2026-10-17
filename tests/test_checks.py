"""검사기가 옳게 도는가.

    uv run python tests/test_checks.py

세 프로젝트가 같은 질문을 한다. **검사 내용만 다르다.**

    review.py --case X     이 분류를 큐에 넣어도 되나     (운영 검사)
    score.py --case X      분류가 정답과 맞았나           (오프라인)
    test_checks.py         **검사기가 제대로 잡나**       (검사기 시험)

## 두 층을 나눈다 — 초판은 섞었고, 그래서 갈라졌다

> ⚠️ 초판의 1번은 검사 셋을 직접 돌리고 확신도를 보고 끝 상태를 **손으로 계산**했다.
> 그건 전달 단계의 로직을 두 번 적은 것이고, **실제로 갈라졌다** —
> 손 계산은 `reject` 라 했는데 흐름도에는 그런 끝 상태가 없었다.

    단위 검사   R1~R3 가 특정 입력을 잡는가        → 모듈을 직접 부른다
    인수 검사   케이스가 어느 끝 상태로 가는가      → **실제 흐름도와 차단 장치를 돌린다**(scripts/flow_check.py)

**정본이 둘이면 언젠가 어긋난다.**
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

from _utf8 import force_utf8  # noqa: E402
from case import Case, find_cases, load_eval  # noqa: E402
from checks import r1_schema, r2_category_valid, r3_evidence_grounded  # noqa: E402
from scoring import escalation_report, score  # noqa: E402

failures: list[str] = []


def ok(label: str, cond: bool) -> None:
    if not cond:
        failures.append(label)
    print(f"   {'OK  ' if cond else 'FAIL'} {label}")


def path_of(name: str) -> Path:
    return next(p for p in find_cases(ROOT / "cases") if p.stem == name)


def case_of(name: str) -> Case:
    return Case.load(path_of(name))


def eval_of(name: str):
    """**테스트만** 정답표를 읽는다. 파이프라인 쪽은 안 부른다."""
    return load_eval(path_of(name))


def good(name: str = "case-01-mixed") -> dict:
    data = json.loads(
        (ROOT / "samples" / "reference" / f"{name}.json").read_text(encoding="utf-8"))
    data.pop("_note", None)
    return data


def variant(fn, name: str = "case-01-mixed") -> dict:
    d = good(name)
    fn(d)
    return d


def expect(label: str, module, data: dict, case: Case, should_pass: bool) -> None:
    r = module.check(data, case)
    good_ = r.passed == should_pass
    if not good_:
        failures.append(f"{label}: {r.guard} 기대 {'통과' if should_pass else '거부'}, 실제 반대")
    want = "통과해야" if should_pass else "잡아야"
    print(f"   {'OK  ' if good_ else 'FAIL'} {r.guard} {r.metric_name:<18} "
          f"{r.format_metric():>5}  {want} | {label}")


# ---------------------------------------------------------------- 1

def graph_verdicts() -> None:
    """케이스가 기대대로 판정되는가 — **실제 흐름도를 돌려서 본다.**

    scripts/flow_check.py 가 이 폴더를 임시 폴더에 복사하고, settings.json 에 등록된 차단 장치를
    Claude Code 와 같은 모양으로 부른다. drafter 자리에는 저장된 분류(samples/)를 쓴다.
    """
    print("1. 흐름 판정이 기대대로인가 (**실제 흐름도**)")

    for path in find_cases(ROOT / "cases"):
        case = Case.load(path)
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / "result.json"
            p = subprocess.run([sys.executable, str(ROOT / "scripts" / "flow_check.py"), "--case", case.name,
                                "--result-json", str(result)],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            got = json.loads(result.read_text(encoding="utf-8")) if result.is_file() else {}
        terminal, code = got.get("terminal") or "?", p.returncode

        want = load_eval(path).expect          # 기대값도 오프라인 쪽에서 읽는다
        good_ = terminal == want
        if not good_:
            failures.append(f"{case.name}: 기대 {want}, 실제 {terminal}")
        print(f"   {'OK  ' if good_ else 'FAIL'} {case.name:<26} "
              f"기대 {want:<12} 실제 {terminal:<12} 종료 {code}")

    # 케이스의 기대값이 흐름도 어휘 안에 있는가 — 이것도 갈라질 수 있다
    import yaml

    terminals = set(yaml.safe_load(
        (ROOT / "graph.yaml").read_text(encoding="utf-8"))["terminal"])
    unknown = [load_eval(p).expect for p in find_cases(ROOT / "cases")
               if load_eval(p).expect not in terminals]
    ok("**케이스의 기대값이 전부 흐름도 끝 상태 안에 있다**", not unknown)


# ---------------------------------------------------------------- 2

def injected() -> None:
    print("\n2. 각 검사가 자기 실패를 잡는가")
    c1 = case_of("case-01-mixed")

    expect("정상 입력", r1_schema, good(), c1, True)
    expect("확신도가 1을 넘었다", r1_schema,
           variant(lambda d: d["classifications"][0].__setitem__("confidence", 1.4)), c1, False)
    expect("근거를 뺐다", r1_schema,
           variant(lambda d: d["classifications"][0].pop("evidence")), c1, False)

    expect("정상 입력", r2_category_valid, good(), c1, True)
    expect("**목록에 없는 카테고리를 지어냈다**", r2_category_valid,
           variant(lambda d: d["classifications"][0].__setitem__("category", "환불요청")),
           c1, False)
    expect("한 문의를 빠뜨렸다", r2_category_valid,
           variant(lambda d: d["classifications"].pop()), c1, False)
    expect("없는 문의 id 를 만들었다", r2_category_valid,
           variant(lambda d: d["classifications"].append(
               {"ticket_id": "T-9999", "category": "bug", "confidence": 0.9,
                "evidence": "없는 티켓"})), c1, False)
    expect("같은 문의를 두 번 분류했다", r2_category_valid,
           variant(lambda d: d["classifications"].append(dict(d["classifications"][0]))),
           c1, False)

    expect("정상 입력", r3_evidence_grounded, good(), c1, True)
    expect("**근거를 요약했다** (본문에 없는 말)", r3_evidence_grounded,
           variant(lambda d: d["classifications"][0].__setitem__(
               "evidence", "고객이 중복 결제를 겪었다")), c1, False)
    expect("근거를 지어냈다", r3_evidence_grounded,
           variant(lambda d: d["classifications"][1].__setitem__(
               "evidence", "환불을 요청했습니다")), c1, False)

    # 검사끼리 못 잡는 것
    wrong_reason = variant(lambda d: d["classifications"][0].__setitem__("category", "account"))
    expect("〃 **근거는 본문에 있는데 분류가 틀렸다**", r3_evidence_grounded,
           wrong_reason, c1, True)
    expect("〃 R2 도 못 잡는다 (account 는 목록 안이다)", r2_category_valid,
           wrong_reason, c1, True)

    c2 = case_of("case-02-unknown-category")
    expect("좁은 목록에서는 bug·howto 가 막힌다", r2_category_valid,
           good("case-02-unknown-category"), c2, False)


# ---------------------------------------------------------------- 3

def offline() -> None:
    print("\n3. 오프라인 채점 — **정답표가 있어야 도는 것**")
    c1 = case_of("case-01-mixed")
    e1 = eval_of("case-01-mixed")
    items = good()["classifications"]

    s = score(items, e1.labels)
    ok(f"정확도 {s.accuracy:.2f}", s.accuracy == 1.0)
    ok("임계값을 넘는다", s.passes(e1.accuracy_threshold))

    wrong = [dict(i) for i in items]
    wrong[0]["category"] = "account"
    s2 = score(wrong, e1.labels)
    ok(f"틀리면 떨어진다 ({s2.accuracy:.2f})", s2.accuracy == 0.75)
    ok("무엇이 틀렸는지 남는다", s2.wrong[0]["ticket_id"] == "T-1041")

    # ⚠️ 초판이 못 잡던 것들 — 전부 정확도를 1.00 으로 만들 수 있었다
    partial = [i for i in items if i["ticket_id"] != "T-1044"]
    s3 = score(partial, e1.labels)
    ok("**빠뜨린 예측이 분모에 남는다** (초판은 사라져서 1.00 이었다)",
       s3.total == 4 and s3.accuracy == 0.75)
    ok("무엇을 빠뜨렸는지 남는다", s3.missing == ["T-1044"])

    dup = items + [dict(items[0])]
    s4 = score(dup, e1.labels)
    ok("**중복 예측을 잡는다**", s4.duplicated == ["T-1041"])
    ok("중복이 있으면 통과시키지 않는다", not s4.passes(0.5))

    extra = items + [{"ticket_id": "T-9999", "category": "bug", "confidence": 0.9,
                      "evidence": "없는 티켓"}]
    s5 = score(extra, e1.labels)
    ok("**라벨 없는 예측은 따로 센다** (분모에 안 넣는다)",
       s5.extra == ["T-9999"] and s5.total == 4)
    ok("그것도 통과시키지 않는다", not s5.passes(0.5))

    s6 = score(items, {})
    ok("**라벨이 없으면 정확도는 None** (0.0 이 아니다)", s6.accuracy is None)
    ok("잴 수 없으면 통과도 아니다", not s6.passes(0.0))

    esc = escalation_report(items, c1.confidence_threshold, e1.expect_escalated)
    ok("확신 낮은 것이 사람 큐로", esc["escalated"] == ["T-1044"])
    ok("놓친 것 없음", not esc["missed"])

    high = escalation_report(items, 0.99, e1.expect_escalated)
    ok(f"**임계값이 높으면 사람 큐가 넘친다** ({high['rate']:.2f})", high["rate"] == 1.0)
    low = escalation_report(items, 0.1, e1.expect_escalated)
    ok("**임계값이 낮으면 애매한 것도 자동으로 나간다**", low["missed"] == ["T-1044"])


# ---------------------------------------------------------------- 4

def assignment_store() -> None:
    """저장소 계약 — **담당은 언제나 하나.**"""
    print("\n4. 담당 저장소 계약 (알림과 대비)")
    from queues import Assignments

    AT = "2026-08-31T00:00:00Z"
    with tempfile.TemporaryDirectory() as tmp:
        a = Assignments(Path(tmp))
        a.assign("T-1041", "billing-team", at=AT, category="billing")
        a.assign("T-1041", "billing-team", at=AT, category="billing")
        ok("**두 번 넣어도 하나다** (덮어쓰기라서)", len(a.all()) == 1)

        a.assign("T-1043", "engineering", at=AT, category="bug")
        ok("다른 티켓은 따로 들어간다", len(a.all()) == 2)
        ok("어느 큐에 있는지 찾을 수 있다", a.where("T-1041") == "billing-team")
        ok("없는 티켓은 None", a.where("T-9999") is None)

        # ⚠️ 초판은 여기서 **양쪽에 남았다.** 지금은 정본이 하나라 옮겨진다.
        a.assign("T-1041", "human-review", at=AT, proposed="billing")
        ok("**다른 큐로 옮기면 이전 큐에서 사라진다**",
           a.where("T-1041") == "human-review" and not a.queue("billing-team"))
        ok("전체 개수는 그대로", len(a.all()) == 2)
        ok("큐별 목록은 정본에서 파생된다",
           a.counts() == {"human-review": 1, "engineering": 1})

        before = a.of("T-1043").to_dict()
        a.assign("T-1043", "engineering", at=AT, category="bug")
        ok("**같은 지정을 다시 하면 기록도 똑같다** (시각을 밖에서 받는 이유)",
           a.of("T-1043").to_dict() == before)

        next(a.root.glob("*.json")).write_text("JSON 아님", encoding="utf-8")
        ok("**깨진 기록이 목록에 드러난다** (조용히 빈 값으로 읽지 않는다)",
           len(a.corrupt()) == 1)


# ---------------------------------------------------------------- 5

def route_crash_resume() -> None:
    """**전달(deliver.py)이 중간에 죽으면.**

    큐에 넣다가 죽었으면 전달을 처음부터 다시 돌린다.
    upsert 라서 같은 상태로 **수렴해야** 한다 — 그걸 여기서 증명한다.
    """
    print("\n5. **전달(deliver.py)이 중간에 죽으면 — 다시 돌린다**")

    import importlib.util

    import queues as q_mod

    spec = importlib.util.spec_from_file_location("deliver", ROOT / "scripts" / "deliver.py")
    deliver_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deliver_mod)

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        rid = "route-crash"
        req = work / "requests" / rid
        req.mkdir(parents=True)
        # 수집·작성·검수를 마친 요청 폴더를 흉내 낸다 — 문의 사본·저장된 분류·케이스 이름
        (req / "state.json").write_text(json.dumps({"id": rid, "case": "case-01-mixed"}), encoding="utf-8")
        (req / "tickets.json").write_text(
            (ROOT / "cases" / "tickets" / "2026-08-31.json").read_text(encoding="utf-8"), encoding="utf-8")
        (req / "draft.json").write_text(json.dumps(good(), ensure_ascii=False), encoding="utf-8")

        real_assign = q_mod.Assignments.assign
        box = {"n": 0}

        def crashing(self, ticket_id, queue, **kw):
            box["n"] += 1
            out = real_assign(self, ticket_id, queue, **kw)
            if box["n"] == 3:          # 세 번째 지정 뒤에 죽는다
                raise RuntimeError("deliver 중간에 죽었다")
            return out

        q_mod.Assignments.assign = crashing
        try:
            try:
                deliver_mod.deliver(req, deliver_mod.Assignments(work / "assignments"))
                failures.append("죽지 않았다")
            except RuntimeError:
                pass
        finally:
            q_mod.Assignments.assign = real_assign

        store = q_mod.Assignments(work / "assignments")
        partial = len(store.all())
        ok(f"죽기 전까지 일부만 들어갔다 ({partial}건)", 0 < partial < 4)

        def rerun() -> int:
            p = subprocess.run([sys.executable, str(ROOT / "scripts" / "deliver.py"), rid, "--root", str(work)],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            return p.returncode

        code = rerun()
        final = store.all()
        ok("**resume 하면 넷 다 들어간다**", len(final) == 4)
        ok("**티켓마다 담당이 정확히 하나다**",
           len({a.ticket_id for a in final}) == 4)
        ok("종착지는 escalated", code == 3)

        snap = lambda: sorted((a.ticket_id, a.queue, a.at) for a in store.all())
        snapshot = snap()
        rerun()
        ok("**다시 돌려도 같은 상태로 수렴한다** (upsert 라서)",
           snap() == snapshot)


def main() -> int:
    force_utf8()
    graph_verdicts()
    injected()
    offline()
    assignment_store()
    route_crash_resume()

    print()
    if failures:
        print(f"실패 {len(failures)}건")
        for line in failures:
            print(f"   {line}")
        return 1
    print("검사기가 기대대로 동작한다.")
    print()
    print("주목할 세 곳:")
    print("  · 1번 — **실제 흐름도를 돌린다.** 끝 상태 계산을 두 번 적지 않는다.")
    print("  · 2번 끝 — **근거가 본문에 있어도 분류가 틀릴 수 있다.**")
    print("    R2·R3 둘 다 통과한다. 그건 정답표(오프라인)나 사람이 잡는다.")
    print("  · 5번 — **전달은 다시 실행돼도 같은 상태로 수렴한다.** upsert 라서다.")
    print("    알림은 그렇지 않았다 — 효과의 모양이 다르면 필요한 장치도 다르다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
