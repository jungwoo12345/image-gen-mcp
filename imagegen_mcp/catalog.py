"""로컬 자산 카탈로그 + 요청↔모델/LoRA 매칭. (로컬 백엔드에서만 의미 있음)

로컬 파일 목록(local.list_assets 의 --list 파싱)과 ~/.image-gen/knowledge/assets.json 의
스타일 메타를 합쳐 요청에 어울리는 후보를 점수화한다. 클라우드 백엔드일 땐 로컬 모델 선택이
없으므로 hint 만 유효하다.
"""
import json
import os
import re

from . import datadir
from .backends import local


def _meta():
    p = datadir.path("assets.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"models": {}, "loras": {}}


def catalog():
    meta = _meta()
    m_meta, l_meta = meta.get("models", {}), meta.get("loras", {})
    assets = local.list_assets()
    models = []
    for key in assets.get("models", []):
        info = m_meta.get(key, {})
        base = key.split(":")[0] if ":" in key else info.get("base")
        models.append({"key": key, "base": base, "tags": info.get("tags", []),
                       "notes": info.get("notes", ""), "rank": info.get("rank", 3)})
    loras = []
    for name in assets.get("loras", []):
        info = l_meta.get(name, {})
        loras.append({"name": name, "base": info.get("base"), "tags": info.get("tags", []),
                      "notes": info.get("notes", ""), "rec_scale": info.get("rec_scale", 0.8)})
    return {"models": models, "loras": loras}


def _tokens(text):
    return re.findall(r"[a-z0-9]+|[가-힣]+", text.lower())


def _score(tokens, tags):
    hits = []
    for tag in tags:
        t = tag.lower()
        for tok in tokens:
            if tok == t or (len(tok) >= 2 and (tok in t or t in tok)):
                hits.append(tag)
                break
    return len(hits), hits


def suggest(request, top=4):
    tokens = _tokens(request)
    cat = catalog()
    sm = []
    for m in cat["models"]:
        s, hits = _score(tokens, m["tags"])
        sm.append((s * 100 + m["rank"], s, hits, m))
    sm.sort(key=lambda x: -x[0])
    sl = []
    for l in cat["loras"]:
        s, hits = _score(tokens, l["tags"])
        if s > 0:
            sl.append((s, hits, l))
    sl.sort(key=lambda x: -x[0])
    best = sm[0][3] if sm else None
    return {
        "request": request,
        "model_candidates": [{"key": m["key"], "base": m["base"], "matched": hits,
                              "style_hits": s, "notes": m["notes"]} for _, s, hits, m in sm[:top]],
        "lora_candidates": [{"name": l["name"], "base": l["base"], "matched": hits,
                             "rec_scale": l["rec_scale"], "notes": l["notes"]} for s, hits, l in sl[:top]],
        "hint": _hint(request, best),
    }


def _hint(request, best):
    tips = []
    r = request.lower()
    if any(k in r for k in ["전신", "fullbody", "full body", "머리부터", "서있", "standing"]):
        tips.append("전신 구도는 832x1216 세로 비율(정사각형이면 잘린다).")
    if any(k in r for k in ["두 명", "두명", "2명", "둘이", "커플", "악수", "handshake", "함께"]):
        tips.append("인물 2명 이상은 한 프롬프트에 넣으면 속성이 섞인다 — 개별 생성 후 합성 권장.")
    if best and best.get("base") == "sdxl":
        tips.append("SDXL 이므로 해상도 1024 이하(8GB VRAM).")
    return " ".join(tips)
