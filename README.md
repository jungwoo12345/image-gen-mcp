# image-gen-mcp

**Claude Code에서 이미지를 만드는 MCP.** 로컬에 NVIDIA GPU(Stable Diffusion) 환경이 있으면
로컬로, 없으면 **무료 클라우드**로 자동 전환해 생성한다. GPU가 없어도 설치·키 없이 바로 쓸 수 있다.

> "○○ 그려줘" → Claude가 자원을 확인하고, 과거 실패 교훈을 참고해, 어울리는 방식으로 생성하고,
> 사용자에게 점수를 받아 **같은 실수를 줄여간다.**

## 백엔드 (자동 선택)

| 백엔드 | 조건 | 특징 |
|---|---|---|
| **무료 클라우드** (기본 폴백) | 인터넷만 | 설치·키·GPU 불필요. 누구나 즉시. 단 **사용 제한 있음**(아래) |
| **로컬 GPU** (있으면 우선) | NVIDIA GPU + createImg 설정 | 무료·오프라인·프라이버시. 로컬 모델/LoRA 사용 가능 |

`~/.image-gen/settings.json` 의 `backend` 로 강제 가능: `auto`(기본) | `local` | `cloud`.

### ⚠️ 무료 클라우드 사용 제한
공용 무료 서비스라 **레이트 리밋/대기열**이 있다. 짧은 시간에 여러 장을 연속 생성하면
**429(제한)** 로 잠시 막히거나 느려질 수 있고, 부하가 크면 일시적으로 실패할 수 있다.
코드가 이를 감지해 1회 재시도 후 안내한다. **대량·안정적 생성이 필요하면 로컬 GPU를 설정**하라.

### 로컬 LoRA/모델은 클라우드로 못 넘어간다
로컬 LoRA·체크포인트는 **당신 디스크의 파일**이라 클라우드(남의 서버)가 접근할 수 없다.
클라우드로 폴백하면 LoRA는 무시되고, 대신 **원하는 화풍을 프롬프트 문구로 표현**하고
클라우드 모델(flux/turbo)을 고른다. (예: 3D LoRA 대신 프롬프트에 `3d render, pixar style`)

## 도구

| 도구 | 역할 |
|---|---|
| `check_resources` | 지금 어떤 백엔드로 생성되는지 + 이유 + 제한 안내 |
| `suggest_assets` | 로컬=모델/LoRA 추천 / 클라우드=스타일 프롬프트+모델 가이드 |
| `list_assets` | 보유 로컬 모델·LoRA(로컬 백엔드) |
| `recall_lessons` | 생성 전 관련 과거 실패·교훈 회상 |
| `search_hf`·`list_repo_files`·`download_asset` | (로컬) HF 검색→용량 고지→허가 후 다운로드 |
| `generate_image` | 생성(백엔드 자동) → run_id·경로 |
| `record_feedback` | 점수(1~10)+오류 지적 → 교훈 승격 |
| `get_history` | 최근 생성 + 피드백 |

## 설치 / 공유

### A) 남에게 공유 (GPU 없어도 됨) — uvx 한 줄
```
claude mcp add image-gen -- uvx --from git+https://github.com/jungwoo12345/image-gen-mcp.git image-gen-mcp
```
받는 사람은 설치·GPU·키 없이 바로 클라우드로 생성. (torch 등 무거운 것 안 받음)

> ⚠️ **`uvx image-gen-mcp`(바 이름)로 설치하지 마세요.** PyPI 에 같은 이름의 **다른(남의) 패키지**가
> 이미 올라와 있어(엉뚱한 코드 = 공급망 위험) 그 이름만 쓰면 다른 게 설치됩니다. **반드시 위처럼
> `--from git+https://github.com/jungwoo12345/image-gen-mcp.git` 로 저장소 주소를 직접 가리켜야** 합니다.
> (uvx 는 절대경로가 필요할 수 있음: `"C:/Users/<이름>/.local/bin/uvx.exe"`)

### B) 로컬 GPU 로 쓰기 (본인)
이미 createImg venv(torch/diffusers)가 있으면 그걸 재사용해 등록한다:
```powershell
E:\ANTIGRAVITY\create_img\venv\Scripts\python.exe -m pip install "mcp>=1.2"
claude mcp add --scope user image-gen -- ^
  E:\ANTIGRAVITY\create_img\venv\Scripts\python.exe -X utf8 ^
  E:\mcp\image-gen\imagegen_mcp\server.py
```
그리고 `~/.image-gen/settings.json` 에 로컬 백엔드 경로를 지정:
```json
{ "backend": "auto",
  "createimg_dir": "E:/ANTIGRAVITY/create_img",
  "venv_python": "E:/ANTIGRAVITY/create_img/venv/Scripts/python.exe" }
```
GPU + 경로가 감지되면 자동으로 로컬 백엔드를 쓴다(없으면 클라우드).

## 표준 흐름
```
요청 → check_resources → recall_lessons → suggest_assets
     → (로컬·자산 부족 시 search_hf → 허가 → download_asset)
     → generate_image → 결과 제시 + 점수/오류 질문 → record_feedback
```

## 데이터 위치 (`~/.image-gen/`)
```
settings.json           백엔드·경로·클라우드 옵션
knowledge/
  lessons.jsonl         누적 교훈(시드 + 피드백 자동 추가) — recall 대상
  LESSONS.md            사람용 렌더(자동)
  assets.json           로컬 자산 스타일 메타(새 모델 받으면 태그 추가)
  runs.jsonl            생성 이력
  feedback.jsonl        점수 피드백
outputs/                생성 이미지
```

## 구조 (개발)
```
imagegen_mcp/
  server.py        FastMCP 도구 + 백엔드 라우팅
  router.py        로컬/클라우드 선택
  backends/
    cloud.py       무료 클라우드(urllib, 키리스) + 레이트리밋 처리
    local.py       createImg 서브프로세스(torch import 안 함 = uvx 호환)
  catalog.py       로컬 자산 매칭
  knowledge.py     이력·피드백·교훈(RAG)
  downloader.py    HF 검색+허가제 다운로드(지연 import)
  datadir.py       ~/.image-gen 경로·설정·시드
  seeds/           기본 lessons.jsonl·assets.json
pyproject.toml     uvx/pip 배포(entry: image-gen-mcp)
```
