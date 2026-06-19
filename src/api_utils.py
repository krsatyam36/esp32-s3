"""Utility endpoints for the Edge Intelligence Platform."""

# ─── Standard Library ───────────────────────────────
import importlib
import os
import platform
import time

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["utilities"])


@router.get("/ping")
async def ping():
    return {"status": "pong", "timestamp": time.time()}


@router.get("/env")
async def env_info():
    safe_keys = ["PATH", "HOME", "USER", "SHELL", "LANG", "PYTHON_VERSION"]
    env = {
        k: v
        for k, v in os.environ.items()
        if k in safe_keys or k.startswith("ESP32") or k.startswith("OLLAMA")
    }
    return {"environment": env}


@router.get("/system")
async def system_info():
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "hostname": platform.node(),
        "cpu_count": os.cpu_count(),
        "pid": os.getpid(),
        "cwd": os.getcwd(),
    }


@router.get("/dependencies")
async def dependencies():
    deps = {
        "cv2": {"status": False, "version": None},
        "numpy": {"status": False, "version": None},
        "requests": {"status": False, "version": None},
        "fastapi": {"status": False, "version": None},
        "uvicorn": {"status": False, "version": None},
        "ultralytics": {"status": False, "version": None, "optional": True},
        "chromadb": {"status": False, "version": None, "optional": True},
        "torch": {"status": False, "version": None, "optional": True},
    }
    for name, info in deps.items():
        try:
            mod = importlib.import_module(name)
            info["status"] = True
            info["version"] = getattr(mod, "__version__", "unknown")
        except ImportError:
            pass
    return {"dependencies": deps}


@router.get("/disk")
async def disk_info():
    stat = os.statvfs(".") if hasattr(os, "statvfs") else None
    if stat:
        total = stat.f_frsize * stat.f_blocks
        free = stat.f_frsize * stat.f_bfree
        used = total - free
        return {
            "total_bytes": total,
            "free_bytes": free,
            "used_bytes": used,
            "usage_pct": round(used / total * 100, 1) if total else 0,
        }
    return {"info": "disk stats not available on this platform"}
