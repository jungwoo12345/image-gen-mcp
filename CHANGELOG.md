# 변경 이력

## v0.1.2 — 2026-07-24
- 🩹 **로컬 생성이 멈췄을 때 자식 프로세스가 정리되지 않던 문제 수정**(수 GB 메모리 누수).
  `_run_cli` 진행률 모드의 타임아웃 검사가 `for line in proc.stdout` **루프 안**에 있어,
  자식이 출력을 멈추고 굳으면 read 에서 블록되어 **검사에 도달조차 못 했다**. 부모는 "생성 실패"로
  반환하는데 자식은 계속 살아남아 좀비가 됐다(실측 14GB 점유).
  → 타임아웃을 **별도 감시 스레드**로 분리하고, `_kill_tree()`(Windows `taskkill /F /T` 로 손자까지)를
  **모든 종료 경로**(정상·예외·타임아웃)에서 호출하도록 수정.
- 교훈: 블로킹 read 와 같은 루프에서 타임아웃을 재지 말 것 — 정작 막으려던 상황에서 무력해진다.

## v0.1.1 — 2026-07-23
- 🩹 로컬 `generate_image` 가 CPU 0% 로 영구 hang 되던 문제 수정.
  `_run_cli` 가 **stdin 을 지정하지 않아** stdio transport MCP 서버의 stdin(JSON-RPC 파이프)을
  자식 `cli.py` 가 상속 → 시작 중 stdin 읽기가 블록됐다. `stdin=subprocess.DEVNULL` 로 해결.
  ★교훈: stdio MCP 서버가 자식 프로세스를 띄울 땐 `stdin=DEVNULL` 이 필수.
- ✨ `cli.py` 의 `[PROGRESS] N` 출력을 파싱해 생성 진행률을 콜백(`progress_cb`).

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
