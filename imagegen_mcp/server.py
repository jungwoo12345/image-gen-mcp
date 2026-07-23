"""image-gen-mcp — 로컬 GPU 있으면 로컬 SD, 없으면 무료 클라우드로 이미지 생성.

Claude 가 "○○ 그려줘" 를 받으면:
  1) check_resources    어떤 백엔드로 생성되는지 확인(로컬 GPU vs 무료 클라우드)
  2) recall_lessons     비슷한 과거 실패·교훈 확인(같은 실수 방지)
  3) suggest_assets     로컬이면 모델/LoRA 추천, 클라우드면 스타일 프롬프트 가이드
     └ recommend_web_search=True 면 → search_hf 로 웹에서 더 나은 LoRA 확보(허가 후 download_asset).
       일반 사용자는 웹 검색을 요청할 줄 모르니, 보유분에 화풍 맞는 게 없으면 자동으로 이 경로를 타라.
  4) generate_image     영어 프롬프트로 생성
  5) 결과를 보여주고 1~10점 + 오류 지적을 물어본 뒤 record_feedback

핵심: 로컬 LoRA/체크포인트는 **로컬 백엔드에서만** 쓸 수 있다. 클라우드로 폴백하면 LoRA 는
불가하므로, 원하는 스타일을 **프롬프트 문구**로 반영하고 클라우드 모델(flux/turbo)을 고른다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

from imagegen_mcp import datadir, router, knowledge, catalog, downloader
from imagegen_mcp.backends import local, cloud

mcp = FastMCP("image-gen")


# ── 자원 / 백엔드 상태 ────────────────────────────────
@mcp.tool()
def check_resources() -> dict:
    """지금 어떤 백엔드로 생성되는지(로컬 GPU vs 무료 클라우드)와 그 이유를 반환한다.
    생성 전에 확인해 해상도·스타일 지정 방식을 정한다."""
    st = router.status()
    if st["active"] == "local":
        st["resources"] = local.resources()
    return st


# ── 자산 / 스타일 선택 ────────────────────────────────
@mcp.tool()
def list_assets() -> dict:
    """보유 로컬 모델/LoRA 목록(로컬 백엔드에서만 의미 있음). 클라우드면 안내를 반환한다."""
    if router.active_name() != "local":
        return {"backend": "cloud",
                "note": "무료 클라우드는 로컬 모델/LoRA 를 쓰지 않는다. 스타일은 프롬프트로 지정하라.",
                "cloud_models": ["flux(기본·고품질)", "turbo(빠름)"]}
    return {"backend": "local", **catalog.catalog()}


@mcp.tool()
def suggest_assets(request: str) -> dict:
    """요청에 어울리는 생성 방법을 추천한다.
    - 로컬 백엔드: 보유 모델/LoRA 후보를 점수순으로(근거 포함).
    - 클라우드 백엔드: 로컬 LoRA 를 못 쓰므로 **스타일을 담을 프롬프트 문구 + 클라우드 모델**을 안내.
    hint(전신 세로비율·다인물 개별생성 등)도 함께 반영하라.

    ★결과에 recommend_web_search=True / next 가 있으면(=보유분에 화풍 맞는 자산 없음),
    사용자가 따로 요청하지 않았어도 next 지시를 따라 search_hf 로 웹에서 더 나은 LoRA/모델을
    찾아라. 일반 사용자는 웹 검색을 요청할 줄 모르므로, 이 에스컬레이션을 건너뛰지 마라."""
    if router.active_name() != "local":
        return {
            "backend": "cloud",
            "note": "무료 클라우드는 로컬 LoRA/체크포인트를 사용할 수 없다. 원하는 화풍을 "
                    "프롬프트 문구로 표현하고 아래 모델을 고르라.",
            "cloud_model_hint": "실사·고품질 → flux(기본) / 빠른 초안·일러스트 → turbo",
            "prompt_style_tip": "화풍을 프롬프트 뒤에 붙여라. 예) '..., 3d render, pixar style' / "
                                "'..., anime illustration, cel shading' / '..., photorealistic, 85mm'",
            "hint": catalog._hint(request, None),
        }
    return {"backend": "local", **catalog.suggest(request)}


# ── 학습 회상 (생성 전 권장) ─────────────────────────
@mcp.tool()
def recall_lessons(request: str) -> list:
    """이 요청과 비슷한 과거 실패·교훈을 반환한다. **생성 전에 호출**해 같은 실수를 피하라.
    (전신→세로비율 / 인물 2명→개별 생성 / 손→시드 변경 등)"""
    return knowledge.recall(request)


# ── 자산 자동 확보 (로컬 백엔드 전용, 허가제) ────────
@mcp.tool()
def search_hf(query: str) -> list:
    """(로컬 전용) Hugging Face 에서 모델/LoRA 후보 검색. repo_id 는 추측 말고 결과의 실제 값 사용."""
    return downloader.search(query)


@mcp.tool()
def list_repo_files(repo_id: str) -> list:
    """(로컬 전용) HF repo 안의 safetensors/ckpt 파일 목록."""
    return downloader.list_files(repo_id)


@mcp.tool()
def download_asset(kind: str, repo_id: str, filename: str, confirm: bool = False) -> dict:
    """(로컬 전용) 모델/LoRA 다운로드. kind = sd15|sdxl|lora.
    대용량이므로 반드시 confirm=False 로 용량을 먼저 고지하고, 사용자 허가 후 confirm=True."""
    return downloader.download(kind, repo_id, filename, confirm)


# ── 생성 ──────────────────────────────────────────────
@mcp.tool()
def generate_image(prompt: str, model: str = "", lora: str = "", lora_scale: float = 0.8,
                   width: int = 0, height: int = 0, steps: int = 30, seed: int = 0) -> dict:
    """이미지를 생성한다(로컬 GPU 되면 로컬, 아니면 무료 클라우드로 자동). prompt 는 **영어**.
    전신은 width=832,height=1216. seed=0 이면 무작위.
    ★로컬 LoRA 는 클라우드에서 무시된다(그 경우 스타일을 프롬프트에 넣어라).

    생성 후 반드시: 결과를 사용자에게 보여주고 **1~10점 + 오류 지적을 요청**한 뒤
    record_feedback(run_id, score, issues, notes) 를 호출하라(학습의 핵심)."""
    backend = router.active()
    name = router.active_name()
    notes = []
    if name == "cloud" and lora:
        notes.append(f"클라우드 백엔드라 LoRA '{lora}' 는 무시됨 — 스타일은 프롬프트로 지정하라.")
        lora = ""
    run = backend.generate(prompt=prompt, model=model, lora=lora, lora_scale=lora_scale,
                           width=width, height=height, steps=steps, seed=seed)
    run.setdefault("params", {})["backend"] = name
    knowledge.record_run(run)
    if run.get("ok"):
        run["next"] = (f"이미지를 사용자에게 보여주고 1~10점 + 오류 지적을 물어본 뒤 "
                       f"record_feedback('{run['run_id']}', 점수, [오류태그], 메모) 를 호출하라.")
    if notes:
        run["backend_notes"] = notes
    return run


# ── 피드백 (학습) ─────────────────────────────────────
@mcp.tool()
def record_feedback(run_id: str, score: int, issues: list = None, notes: str = "") -> dict:
    """사용자 점수(1~10)+오류 지적을 기록. 점수 낮거나(≤6) 오류 있으면 교훈으로 승격돼
    다음 recall_lessons 에 반영된다. issues 예: ['손붕괴','속성뒤섞임','화풍불일치','잘림']."""
    return knowledge.record_feedback(run_id, score, issues or [], notes)


@mcp.tool()
def get_history(limit: int = 10) -> list:
    """최근 생성 이력 + 각 건의 점수 피드백."""
    return knowledge.history(limit)


def main():
    datadir.ensure()
    mcp.run()


if __name__ == "__main__":
    main()
