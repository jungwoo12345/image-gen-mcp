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


def _tok_match(tok, word):
    """토큰 하나가 태그 단어 하나와 맞는가. 부분문자열 오탐(art⊂cartoon)을 막기 위해
    동일하거나, 둘 다 3자 이상이고 한쪽이 다른 쪽의 '접두'일 때만 매칭한다."""
    if tok == word:
        return True
    if len(tok) >= 3 and len(word) >= 3 and (tok.startswith(word) or word.startswith(tok)):
        return True
    return False


def _score(tokens, tags):
    hits = []
    for tag in tags:
        words = _tokens(tag)  # 다단어 태그("cartoon 3d")를 단어별로 분해해 단어 단위 비교
        if any(_tok_match(tok, w) for tok in tokens for w in words):
            hits.append(tag)
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
    best_model_hits = sm[0][1] if sm else 0
    # 보유분에 요청 스타일과 맞는 게 없으면(모델 태그 0매치 + 매칭 LoRA 0) 웹 확보를 권한다.
    # 일반 사용자는 "웹에서 찾아줘"라고 말할 줄 모르므로, 여기서 에스컬레이션을 명시한다.
    local_weak = (best_model_hits == 0) and (len(sl) == 0)
    out = {
        "request": request,
        "model_candidates": [{"key": m["key"], "base": m["base"], "matched": hits,
                              "style_hits": s, "notes": m["notes"]} for _, s, hits, m in sm[:top]],
        "lora_candidates": [{"name": l["name"], "base": l["base"], "matched": hits,
                             "rec_scale": l["rec_scale"], "notes": l["notes"]} for s, hits, l in sl[:top]],
        "hint": _hint(request, best),
        "local_match": "weak" if local_weak else "ok",
    }
    if local_weak:
        out["recommend_web_search"] = True
        out["next"] = (
            "보유 자산 중 이 요청의 화풍에 맞는 모델/LoRA 가 없다. 사용자가 웹 검색을 "
            "요청하지 않았더라도, 더 나은 결과를 위해 search_hf('<영어 스타일 키워드>') 로 "
            "HF 에서 어울리는 LoRA/체크포인트를 찾아라. 좋은 후보가 있으면 용량을 고지하고 "
            "사용자 허가를 받아 download_asset 으로 확보한 뒤 생성하라. 적절한 게 없거나 "
            "사용자가 원치 않으면, 보유 베이스 모델 + 프롬프트 문구로 화풍을 최대한 살려 생성하라."
        )
    return out


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
