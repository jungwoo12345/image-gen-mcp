"""학습 저장소 — 생성 이력·점수 피드백·교훈(RAG). 백엔드 무관하게 공통.

데이터는 ~/.image-gen/knowledge/ 에 둔다(uvx 격리 환경에서도 영속).
"""
import json
import os
import re
import time

from . import datadir


def _p(name):
    return datadir.path(name)


def _append(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _read(path):
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _tokens(text):
    return re.findall(r"[a-z0-9]+|[가-힣]+", (text or "").lower())


# ── 이력 ──────────────────────────────────────────────
def record_run(run: dict):
    datadir.ensure()
    _append(_p("runs.jsonl"), {
        "run_id": run.get("run_id"), "ts": _now(), "ok": run.get("ok"),
        "output": run.get("output"), "elapsed_sec": run.get("elapsed_sec"),
        "params": run.get("params", {}), "error": run.get("error")})


def _find_run(run_id):
    for r in reversed(_read(_p("runs.jsonl"))):
        if r.get("run_id") == run_id:
            return r
    return None


# ── 피드백 ────────────────────────────────────────────
def record_feedback(run_id, score, issues=None, notes=""):
    datadir.ensure()
    issues = issues or []
    _append(_p("feedback.jsonl"), {"run_id": run_id, "ts": _now(), "score": score,
                                   "issues": issues, "notes": notes})
    run = _find_run(run_id)
    prompt = (run or {}).get("params", {}).get("prompt", "")
    promoted = None
    if (isinstance(score, int) and score <= 6) or issues:
        symptom = f"점수 {score}/10." + (f" 지적: {', '.join(issues)}." if issues else "")
        if notes:
            symptom += f" {notes}"
        if prompt:
            symptom += f" (프롬프트: {prompt[:120]})"
        tags = list(issues) + _tokens(prompt)[:8]
        promoted = add_lesson(tags, symptom,
                              notes or "다음 생성 시 파라미터/구도를 조정할 것.",
                              f"feedback:{run_id}", score)
    return {"recorded": True, "promoted_to_lesson": bool(promoted)}


# ── 교훈 ──────────────────────────────────────────────
def add_lesson(tags, symptom, fix, source="", score=None):
    datadir.ensure()
    lesson = {"id": f"fb-{int(time.time())}", "ts": _now(),
              "tags": [t for t in tags if t], "symptom": symptom, "fix": fix, "source": source}
    if score is not None:
        lesson["score"] = score
    _append(_p("lessons.jsonl"), lesson)
    _render_md()
    return lesson


def recall(request, top=5):
    datadir.ensure()
    tokens = set(_tokens(request))

    def _hit(t, tok):
        t = t.lower()
        return tok == t or (len(tok) >= 2 and tok in t) or (len(t) >= 2 and t in tok)

    scored = []
    for l in _read(_p("lessons.jsonl")):
        hay = " ".join(l.get("tags", [])) + " " + l.get("symptom", "")
        htoks = set(_tokens(hay))
        tag_hits = sum(1 for t in l.get("tags", []) for tok in tokens if _hit(t, tok))
        s = tag_hits * 3 + len(tokens & htoks)
        if s > 0:
            scored.append((s, l))
    scored.sort(key=lambda x: -x[0])
    return [{"symptom": l["symptom"], "fix": l["fix"], "source": l.get("source", "")}
            for _, l in scored[:top]]


def history(limit=10):
    datadir.ensure()
    fbs = {}
    for f in _read(_p("feedback.jsonl")):
        fbs.setdefault(f["run_id"], []).append(f)
    out = []
    for r in reversed(_read(_p("runs.jsonl"))):
        rid = r.get("run_id")
        out.append({"run_id": rid, "ts": r.get("ts"), "ok": r.get("ok"),
                    "output": r.get("output"),
                    "params": {k: v for k, v in r.get("params", {}).items() if v is not None},
                    "feedback": fbs.get(rid, [])})
        if len(out) >= limit:
            break
    return out


def _render_md():
    lessons = _read(_p("lessons.jsonl"))
    lines = ["# 이미지 생성 교훈 (자동 생성)", "",
             "> 같은 실수를 반복하지 않기 위한 누적 기록. 생성 전 recall_lessons 로 참조된다.",
             f"> 총 {len(lessons)}건.", ""]
    for l in lessons:
        lines.append(f"## {l.get('id')} · {l.get('source', '')}")
        if l.get("ts") and l["ts"] != "seed":
            lines.append(f"_{l['ts']}_")
        lines.append(f"- **증상**: {l.get('symptom', '')}")
        lines.append(f"- **대응**: {l.get('fix', '')}")
        tags = ", ".join(l.get("tags", [])[:10])
        if tags:
            lines.append(f"- _tags_: {tags}")
        lines.append("")
    with open(_p("LESSONS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
