"""Hugging Face 검색 + 허가제 다운로드. (로컬 백엔드 전용)

huggingface_hub 는 로컬 GPU 사용자의 createImg venv 에 있다. MCP 서버가 uvx 격리 환경에서
돌 수도 있으므로 **지연 import** 하고, 없으면 안내한다(클라우드 사용자는 이 도구가 필요 없음).
"""
import os

from .backends import local


def _hf():
    try:
        from huggingface_hub import HfApi
        return HfApi()
    except ImportError:
        return None


def search(query, limit=8):
    api = _hf()
    if api is None:
        return [{"error": "huggingface_hub 없음 — 로컬 백엔드(createImg venv)에서만 다운로드 가능."}]
    try:
        res = api.list_models(search=query, sort="downloads", direction=-1, limit=limit)
        return [{"repo_id": m.id, "downloads": getattr(m, "downloads", None),
                 "likes": getattr(m, "likes", None)} for m in res]
    except Exception as e:
        return [{"error": f"HF 검색 실패: {e}"}]


def list_files(repo_id):
    api = _hf()
    if api is None:
        return ["huggingface_hub 없음"]
    try:
        return [f for f in api.list_repo_files(repo_id)
                if f.lower().endswith((".safetensors", ".ckpt"))]
    except Exception as e:
        return [f"오류: {e}"]


def _target(kind):
    md = local.models_dir()
    if not md:
        return ""
    sub = {"sd15": "sd15", "sdxl": "sdxl", "lora": "loras", "loras": "loras"}.get(kind, "")
    return os.path.join(md, sub) if sub else ""


def download(kind, repo_id, filename, confirm=False):
    target = _target(kind)
    if not target:
        return {"ok": False, "error": "로컬 모델 폴더를 찾지 못함(로컬 백엔드 미설정)."}
    size_mb = None
    try:
        from huggingface_hub import get_hf_file_metadata, hf_hub_url
        meta = get_hf_file_metadata(hf_hub_url(repo_id=repo_id, filename=filename))
        if meta.size:
            size_mb = round(meta.size / (1024 ** 2), 1)
    except Exception:
        pass
    dest = os.path.join(target, filename)
    if not confirm:
        return {"ok": True, "needs_confirm": True,
                "would_download": {"repo_id": repo_id, "filename": filename,
                                   "size_mb": size_mb, "save_to": dest},
                "message": f"다운로드 예정: {filename} ({size_mb}MB 예상) → {dest}. "
                           f"사용자 허가 후 confirm=True 로 다시 호출하라."}
    try:
        from huggingface_hub import hf_hub_download
        os.makedirs(target, exist_ok=True)
        path = hf_hub_download(repo_id=repo_id, filename=filename, local_dir=target)
        return {"ok": True, "downloaded": path, "size_mb": size_mb,
                "note": "다음 생성부터 --list 에 나타난다. assets.json 에 스타일 태그를 추가하면 추천에 반영."}
    except Exception as e:
        return {"ok": False, "error": f"다운로드 실패: {e}",
                "hint": "repo_id/filename 을 search()/list_files() 결과의 실제 값으로 확인하라."}
