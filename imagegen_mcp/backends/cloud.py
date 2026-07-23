"""무료 클라우드 백엔드 — 키·GPU·설치 불필요(표준 라이브러리 urllib 만 사용).

기본 제공자는 pollinations(무료·키리스). GPU 가 없는 사람도 바로 이미지를 만들 수 있게 하는
폴백 백엔드다. 프롬프트는 영어로 받는다(호출자가 변환).
"""
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import datadir


def available() -> bool:
    """인터넷만 되면 사용 가능. 여기서는 항상 True 로 두고 실패는 생성 시 처리."""
    return True


def info() -> dict:
    s = datadir.settings()["cloud"]
    return {"backend": "cloud", "provider": s.get("provider"), "model": s.get("model"),
            "note": "키·GPU 불필요(무료). 로컬 GPU 환경을 설정하면 로컬 백엔드가 우선한다.",
            "limits": ("공용 무료 서비스라 레이트 리밋/대기열이 있다. 짧은 시간에 여러 장을 "
                       "연속 생성하면 429(제한)로 잠시 막히거나 느려질 수 있고, 부하가 크면 "
                       "일시적으로 실패할 수 있다. 대량·안정적 생성이 필요하면 로컬 GPU 를 설정하라.")}


def generate(prompt: str, width: int = 0, height: int = 0, seed: int = 0,
             model: str = "", steps: int = 0, timeout: int = 120, **_) -> dict:
    s = datadir.settings()["cloud"]
    base = s.get("base_url", "https://image.pollinations.ai/prompt/")
    model = model or s.get("model", "flux")

    w = width or 1024
    h = height or 1024
    q = {"width": w, "height": h, "nologo": "true", "model": model}
    if seed:
        q["seed"] = seed
    url = base + urllib.parse.quote(prompt, safe="") + "?" + urllib.parse.urlencode(q)

    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(datadir.OUTPUTS, f"{run_id}.jpg")
    os.makedirs(datadir.OUTPUTS, exist_ok=True)

    params = {"prompt": prompt, "backend": "cloud", "provider": s.get("provider"),
              "model": model, "width": w, "height": h, "seed": seed or None}
    t0 = time.time()

    # 공용 무료 서비스라 429(제한)·5xx(혼잡)가 날 수 있다 → 짧게 1회 재시도 후 친절히 안내.
    last_err = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "image-gen-mcp/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                ctype = r.headers.get("Content-Type", "")
            if not data or not ctype.startswith("image"):
                last_err = f"이미지 응답 아님(Content-Type={ctype})"
                break
            with open(out_path, "wb") as f:
                f.write(data)
            return {"ok": True, "run_id": run_id, "output": out_path,
                    "elapsed_sec": round(time.time() - t0, 1), "params": params}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = e.headers.get("Retry-After")
                wait = int(retry_after) if (retry_after and retry_after.isdigit()) else 6
                if attempt == 0:
                    time.sleep(min(wait, 15))
                    continue
                return {"ok": False, "run_id": run_id, "params": params, "rate_limited": True,
                        "error": "무료 클라우드가 사용 제한(429)에 걸렸다. 잠시 후 다시 시도하거나, "
                                 "대량 생성이 필요하면 로컬 GPU 를 설정하라."}
            last_err = f"HTTP {e.code}"
            if 500 <= e.code < 600 and attempt == 0:
                time.sleep(4); continue
            break
        except Exception as e:
            last_err = str(e)
            if attempt == 0:
                time.sleep(3); continue
            break

    return {"ok": False, "run_id": run_id, "params": params,
            "error": f"클라우드 생성 실패: {last_err}. 무료 서비스가 혼잡하거나 일시 장애일 수 "
                     f"있다 — 잠시 후 재시도하거나 로컬 GPU 를 설정하라."}
