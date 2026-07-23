"""백엔드 선택 — 로컬 GPU 되면 로컬, 안 되면 무료 클라우드.

settings.backend: auto(기본) | local | cloud
  auto  → 로컬 사용 가능하면 local, 아니면 cloud
  local → 강제 로컬(안 되면 에러 메시지)
  cloud → 강제 클라우드
"""
from . import datadir
from .backends import cloud, local


def active_name() -> str:
    pref = datadir.settings().get("backend", "auto")
    if pref == "cloud":
        return "cloud"
    if pref == "local":
        return "local"
    return "local" if local.available() else "cloud"


def active():
    return local if active_name() == "local" else cloud


def status() -> dict:
    name = active_name()
    return {
        "active": name,
        "local_available": local.available(),
        "cloud_available": cloud.available(),
        "detail": (local.info() if name == "local" else cloud.info()),
        "explain": ("로컬 GPU 환경이 감지돼 로컬로 생성합니다." if name == "local"
                    else "로컬 GPU 환경이 없어(또는 cloud 강제) 무료 클라우드로 생성합니다."),
    }
