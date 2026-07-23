"""로컬 GPU 백엔드 — createImg(Stable Diffusion) 를 서브프로세스로 호출.

MCP 서버 프로세스 자체는 torch 를 import 하지 않는다(uvx 격리 환경에서도 돌아야 하므로).
모든 무거운 연산은 createImg venv python 으로 cli.py 를 실행해 위임한다.
자산 목록도 `cli.py --list` 를 파싱해 얻는다(config import 안 함 = 완전 분리).
"""
import os
import re
import shutil
import subprocess
import time

from .. import datadir

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _paths():
    s = datadir.settings()
    return s.get("createimg_dir", ""), s.get("venv_python", "")


def _gpu() -> dict | None:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8",
            timeout=15, creationflags=_CREATE_NO_WINDOW)
        line = (r.stdout or "").strip().splitlines()[0]
        name, total, free = [x.strip() for x in line.split(",")]
        return {"name": name, "vram_total_mb": int(float(total)),
                "vram_free_mb": int(float(free))}
    except Exception:
        return None


def available() -> bool:
    """createImg 경로 + venv python + GPU 가 모두 있어야 로컬 백엔드 사용 가능."""
    d, py = _paths()
    if not (d and os.path.isfile(os.path.join(d, "cli.py")) and py and os.path.isfile(py)):
        return False
    return _gpu() is not None


def info() -> dict:
    d, py = _paths()
    g = _gpu()
    return {"backend": "local", "createimg_dir": d, "gpu": g,
            "note": "로컬 GPU 로 생성(무료·오프라인·프라이버시)."}


def resources() -> dict:
    d, py = _paths()
    out = {"gpu": _gpu(), "venv_ok": bool(py) and os.path.isfile(py),
           "createimg_ok": bool(d) and os.path.isfile(os.path.join(d, "cli.py")),
           "disk": None, "guidance": []}
    if out["gpu"] and out["gpu"]["vram_total_mb"] <= 8192:
        out["guidance"].append("VRAM 8GB급 — SDXL 은 offload, 1024 초과 금지. 전신은 832x1216.")
    if d:
        md = os.path.join(d, "models")
        try:
            free_gb = shutil.disk_usage(md).free / (1024 ** 3)
            out["disk"] = {"path": md, "free_gb": round(free_gb, 1)}
            if free_gb < 15:
                out["guidance"].append(f"모델 폴더 여유 {free_gb:.1f}GB — SDXL 1개 ≈ 7GB.")
        except Exception:
            pass
    return out


def models_dir() -> str:
    d, _ = _paths()
    return os.path.join(d, "models") if d else ""


def _run_cli(args: list, timeout: int, progress_cb=None) -> subprocess.CompletedProcess:
    d, py = _paths()
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    cmd = [py, "-X", "utf8", "cli.py", *args]
    if progress_cb is None:
        return subprocess.run(cmd, cwd=d, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env=env,
                              creationflags=_CREATE_NO_WINDOW)
    # 진행률 콜백 모드: 줄 단위로 읽으며 cli.py 의 "[PROGRESS] N" 을 파싱해 콜백한다.
    import re
    import time as _time
    proc = subprocess.Popen(cmd, cwd=d, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            env=env, creationflags=_CREATE_NO_WINDOW)
    lines, t0 = [], _time.time()
    try:
        for line in proc.stdout:
            lines.append(line)
            m = re.search(r"\[PROGRESS\]\s*(\d+)", line)
            if m:
                try:
                    progress_cb(int(m.group(1)))
                except Exception:
                    pass
            if _time.time() - t0 > timeout:
                proc.kill()
                raise subprocess.TimeoutExpired(cmd, timeout)
    finally:
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    r = subprocess.CompletedProcess(cmd, proc.returncode or 0,
                                    stdout="".join(lines), stderr="")
    return r


def list_assets() -> dict:
    """`cli.py --list` 를 파싱해 모델/LoRA 목록을 반환(config import 없이)."""
    try:
        r = _run_cli(["--list"], timeout=60)
    except Exception as e:
        return {"models": [], "loras": [], "error": str(e)}
    models, loras, section = [], [], None
    for raw in (r.stdout or "").splitlines():
        line = raw.rstrip()
        if line.startswith("[모델]"):
            section = "m"; continue
        if line.startswith("[LoRA]"):
            section = "l"; continue
        if re.match(r"^  \S", line):        # 2칸 들여쓰기 = 항목명
            name = line.strip()
            if section == "m":
                models.append(name)
            elif section == "l":
                loras.append(name)
    return {"models": models, "loras": loras}


def generate(prompt: str, model: str = "sdxl:RealVisXL_V4.0.safetensors",
             lora: str = "", lora_scale: float = 0.8,
             width: int = 0, height: int = 0, steps: int = 30, seed: int = 0,
             ref_images=None, ref_scale: float = 0.6,
             progress_cb=None, timeout: int = 900, **_) -> dict:
    d, py = _paths()
    if not available():
        return {"ok": False, "error": "로컬 백엔드 사용 불가(createImg/venv/GPU 확인)."}
    model = model or "sdxl:RealVisXL_V4.0.safetensors"

    run_id = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(datadir.OUTPUTS, exist_ok=True)
    out_path = os.path.join(datadir.OUTPUTS, f"{run_id}.png")

    args = ["--eng", prompt, "--model", model, "--steps", str(steps or 30), "--out", out_path]
    if lora:
        args += ["--lora", lora, "--lora-scale", str(lora_scale)]
    if width:
        args += ["--width", str(width)]
    if height:
        args += ["--height", str(height)]
    if seed:
        args += ["--seed", str(seed)]
    # 참고 이미지(IP-Adapter, 여러 장) — 존재하는 파일만 전달
    refs = [str(p) for p in (ref_images or []) if p and os.path.isfile(str(p))]
    if refs:
        args += ["--ref", *refs, "--ref-scale", str(ref_scale)]

    params = {"prompt": prompt, "backend": "local", "model": model, "lora": lora or None,
              "lora_scale": lora_scale, "width": width or None, "height": height or None,
              "steps": steps or 30, "seed": seed or None}
    t0 = time.time()
    try:
        r = _run_cli(args, timeout=timeout, progress_cb=progress_cb)
    except subprocess.TimeoutExpired:
        return {"ok": False, "run_id": run_id, "error": f"생성 시간초과({timeout}s)", "params": params}

    if r.returncode != 0 or not os.path.isfile(out_path):
        tail = (r.stderr or r.stdout or "").strip()[-1500:]
        return {"ok": False, "run_id": run_id, "error": "생성 실패", "log": tail, "params": params}
    return {"ok": True, "run_id": run_id, "output": out_path,
            "elapsed_sec": round(time.time() - t0, 1), "params": params}
