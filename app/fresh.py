"""배포 앱이 재시작 없이 새 코드를 받을 때 남는 낡은 모듈을 다시 읽는다.

Streamlit은 페이지 스크립트는 매번 새로 실행하지만, sim/·agents/ 같은 저장소 모듈과 이미 불러온
common.py 는 프로세스가 살아 있는 동안 처음 읽은 버전이 메모리에 남는다. 새 커밋이 들어오면
새 페이지 코드가 옛 모듈을 불러 '없는 지표' 같은 오류가 난다 (예: METRICS에 process_days 없음).
페이지 맨 위에서 ensure()를 부르면, 소스 파일이 메모리의 버전보다 새로운 프로젝트 모듈을
의존 순서대로 다시 읽고 시뮬레이션 캐시를 비운다.
"""
from __future__ import annotations

import importlib
import os
import sys
import time
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
PKGS = ("sim", "agents", "rag", "collector", "geo")
TOP = ("i18n", "common", "case_trace")    # app/ 안의 공통 모듈: 마지막에 이 순서로 다시 읽는다
FIRST = ("sim.cases", "sim.calibration", "sim.engine", "sim.metrics")
_loaded: dict[str, float] = {}   # 모듈 이름 → 메모리에 있는 버전의 소스 파일 수정 시각


def _ours(name: str, mod) -> bool:
    f = getattr(mod, "__file__", None)
    return bool(f) and (name in TOP or name.split(".")[0] in PKGS) and os.path.abspath(f).startswith(ROOT)


def _mtime(mod) -> float:
    try:
        return os.path.getmtime(mod.__file__)
    except OSError:
        return 0.0


def _process_start() -> float:
    """이 프로세스가 시작된 시각 (리눅스). 모르면 지금 시각을 써서 아무것도 다시 읽지 않는다."""
    try:
        with open(f"/proc/{os.getpid()}/stat") as f:
            ticks = float(f.read().rsplit(")", 1)[1].split()[19])
        with open("/proc/uptime") as f:
            uptime = float(f.read().split()[0])
        return time.time() - uptime + ticks / os.sysconf("SC_CLK_TCK")
    except Exception:  # noqa: BLE001
        return time.time()


_START = _process_start()


def _order(names: list[str]) -> list[str]:
    first = [n for n in FIRST if n in names]
    top = [n for n in TOP if n in names]
    return first + sorted(n for n in names if n not in first and n not in top) + top


def ensure() -> list[str]:
    mods = {n: m for n, m in list(sys.modules.items()) if m is not None and _ours(n, m)}
    changed = [n for n, m in mods.items() if _mtime(m) > _loaded.get(n, _START)]
    reloaded = []
    if changed:
        # 바뀐 모듈을 불러 쓰는 모듈도 옛 객체를 들고 있으므로 프로젝트 모듈을 모두 다시 읽는다.
        for n in _order(list(mods)):
            try:
                importlib.reload(sys.modules[n])
                reloaded.append(n)
            except Exception:  # noqa: BLE001  다시 읽기에 실패하면 기존 모듈로 계속
                pass
        try:
            import streamlit as st
            st.cache_data.clear()
        except Exception:  # noqa: BLE001
            pass
    for n, m in mods.items():
        _loaded[n] = max(_mtime(m), _loaded.get(n, _START))
    return reloaded
