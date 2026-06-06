"""Utility endpoints for the Edge Intelligence Platform."""

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
