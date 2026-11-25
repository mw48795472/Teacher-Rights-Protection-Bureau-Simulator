"""구조별 지역 데이터 묶음. 구조 YAML의 region(기본 경기)으로 고른다."""
from __future__ import annotations

from . import gyeonggi, incheon

REGIONS = {"경기": gyeonggi, "인천": incheon}
DEFAULT = "경기"


def region_of(structure: dict) -> str:
    r = structure.get("region", DEFAULT)
    return r if r in REGIONS else DEFAULT


def module(region: str):
    return REGIONS.get(region, REGIONS[DEFAULT])
