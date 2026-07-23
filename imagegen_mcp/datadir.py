"""사용자 데이터 경로 + 설정. uvx 격리 환경에서도 영속하도록 ~/.image-gen 에 둔다.

- settings.json : 백엔드 선택·createImg 경로·클라우드 옵션
- knowledge/    : lessons.jsonl · assets.json · runs.jsonl · feedback.jsonl · LESSONS.md
- outputs/      : 생성 이미지

패키지 seeds/ 의 lessons.jsonl·assets.json 을 최초 실행 시 복사해 시드한다.
"""
import json
import os
import shutil

HOME = os.path.expanduser("~")
BASE = os.environ.get("IMAGEGEN_DATA_DIR", os.path.join(HOME, ".image-gen"))
KDIR = os.path.join(BASE, "knowledge")
OUTPUTS = os.path.join(BASE, "outputs")
SETTINGS_PATH = os.path.join(BASE, "settings.json")

_PKG = os.path.dirname(os.path.abspath(__file__))
_SEEDS = os.path.join(_PKG, "seeds")

DEFAULT_SETTINGS = {
    "backend": "auto",              # auto | local | cloud
    "createimg_dir": "",            # 로컬 백엔드: createImg 폴더(비면 로컬 비활성)
    "venv_python": "",              # 로컬 백엔드: createImg venv python 절대경로
    "cloud": {
        "provider": "pollinations", # 키 없는 무료 백엔드
        "model": "flux",            # flux | turbo 등(provider 지원값)
        "base_url": "https://image.pollinations.ai/prompt/",
    },
    "defaults": {"steps": 30, "width": 0, "height": 0},
}


def ensure() -> None:
    os.makedirs(KDIR, exist_ok=True)
    os.makedirs(OUTPUTS, exist_ok=True)
    # 시드 복사(없을 때만)
    for name in ("lessons.jsonl", "assets.json"):
        dst = os.path.join(KDIR, name)
        src = os.path.join(_SEEDS, name)
        if not os.path.exists(dst) and os.path.exists(src):
            shutil.copyfile(src, dst)
    for name in ("runs.jsonl", "feedback.jsonl"):
        p = os.path.join(KDIR, name)
        if not os.path.exists(p):
            open(p, "a").close()
    if not os.path.exists(SETTINGS_PATH):
        save_settings(DEFAULT_SETTINGS)


def settings() -> dict:
    ensure()
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            s.update(json.load(f))
    except Exception:
        pass
    # 환경변수 오버라이드
    s["backend"] = os.environ.get("IMAGEGEN_BACKEND", s.get("backend", "auto"))
    s["createimg_dir"] = os.environ.get("IMAGEGEN_CREATEIMG_DIR", s.get("createimg_dir", ""))
    s["venv_python"] = os.environ.get("IMAGEGEN_VENV_PYTHON", s.get("venv_python", ""))
    s.setdefault("cloud", DEFAULT_SETTINGS["cloud"])
    s.setdefault("defaults", DEFAULT_SETTINGS["defaults"])
    return s


def save_settings(s: dict) -> None:
    os.makedirs(BASE, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def path(*parts) -> str:
    return os.path.join(KDIR, *parts)
