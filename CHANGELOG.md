# 변경 이력

## v0.1.0 — 2026-07-23
- 첫 릴리스.
- **듀얼 백엔드 자동 선택**: 로컬 NVIDIA GPU(Stable Diffusion/createImg)가 있으면 로컬로,
  없으면 **무료 클라우드**(pollinations, 키·설치 불필요)로 이미지 생성.
- 도구 10개: check_resources · list_assets · suggest_assets · recall_lessons ·
  search_hf · list_repo_files · download_asset · generate_image · record_feedback · get_history.
- **학습 루프**: 생성물에 1~10점 + 오류 지적 → 교훈으로 남겨 다음 생성 시 recall(같은 실수 방지).
  교훈은 createImg 실전 사례(속성 뒤섞임·손 붕괴·전신 잘림 등)로 시드.
- 로컬 백엔드는 createImg 를 서브프로세스로 호출(서버 자체는 torch 불필요 → uvx 배포 호환).
- 무료 클라우드 레이트 리밋 감지·재시도·안내.
- 데이터는 `~/.image-gen/` 에 영속(설정·학습기록·이미지).
