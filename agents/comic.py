"""결정적 장면을 만화 컷으로 (인물 아이콘 + 말풍선 + 판정 도장).

설명 문장은 빼고, 컷마다 '어디서 / 누가 / 한마디 / 판정 도장'만 남긴다.
대사는 드라마 대본(build_script)의 것을 그대로 쓰고, 컷 고르기는 digest.key_moments를 따른다.
"""
from __future__ import annotations

from html import escape

from . import digest
from .drama import PLACE, build_script
from .relmap import GROUP, NODE
from .runner import AgentRun

STAMP = {  # 배지 → (도장 글자, 색)
    "차단": ("✕ 법에 막힘", "#d64541"), "침해": ("⚠ 교권 침해", "#8b5cf6"), "조건부": ("△ 조건부", "#e67e22"),
    "흘러감": ("… 아무도 안 챙김", "#d64541"), "허용": ("", ""),
}
FINAL = {"사안종결"}

CSS = """<style>
.cm-grid {display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); margin: 6px 0 4px;}
.cm {position: relative; border: 3px solid #222; border-radius: 6px; padding: 30px 12px 14px; min-height: 190px;
     background: #fffdf6; color: #222; box-shadow: 4px 4px 0 rgba(0,0,0,.18); overflow: hidden; word-break: keep-all;}
.cm .no {position: absolute; top: 0; left: 0; background: #222; color: #fff; font-weight: 800; font-size: .78rem;
         padding: 2px 9px; border-bottom-right-radius: 6px;}
.cm .pl {position: absolute; top: 0; right: 0; background: #ffe066; color: #222; font-size: .72rem; font-weight: 700;
         padding: 2px 8px; border-left: 2px solid #222; border-bottom: 2px solid #222;}
.cm .who {display: flex; align-items: center; gap: 8px; margin-top: 16px;}
.cm .face {width: 52px; height: 52px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
           font-size: 30px; border: 2.5px solid; flex: none;}
.cm .nm {font-weight: 800; font-size: .85rem;}
.cm .bub {position: relative; background: #fff; border: 2.5px solid #222;
          border-radius: 16px; padding: 7px 11px; font-size: .9rem; font-weight: 600; line-height: 1.35;}
.cm .bub:after {content: ""; position: absolute; left: 26px; bottom: -12px; border: 6px solid transparent;
                border-top: 8px solid #222;}
.cm .stamp {position: absolute; right: 10px; bottom: 12px; transform: rotate(-9deg); border: 3px solid; border-radius: 6px;
            padding: 2px 8px; font-weight: 900; font-size: .9rem; background: rgba(255,255,255,.85); letter-spacing: .02em;}
.cm.blk {background: repeating-linear-gradient(135deg, #fff5f4, #fff5f4 10px, #ffecea 10px, #ffecea 20px);}
.cm.end {background: #eef5ff;}
</style>"""


def _face(actor: str) -> tuple[str, str]:
    g, emoji, name = NODE.get(actor, ("school", "🙂", actor))
    return emoji, GROUP[g]


def _short_line(line: str, n: int = 46) -> str:
    line = (line or "").strip()
    return line if len(line) <= n else line[: n - 1].rstrip() + "…"


def _trip(why: str) -> int:
    """'선생님이 직접 찾아간 n번째 곳' → n (없으면 0)."""
    import re
    hit = re.search(r"찾아간 (\d+)번째", why or "")
    return int(hit.group(1)) if hit else 0


def panels(run: AgentRun, scenario_name: str = "") -> list[dict]:
    """컷 목록. 컷 하나 = {no, place, actor, intent, line, badge, skip(앞에서 건너뛴 무난한 장면 수)}."""
    lines = {x.no: x for _, xs in build_script(run, scenario_name).acts for x in xs}
    out, skip = [], 0
    for m in digest.key_moments(run):
        if isinstance(m, digest.Flow):
            skip += len(m.steps)   # 별일 없던 절차는 다음 컷 번호 옆에 '⋯ n' 으로만
            continue
        sc = lines.get(m.no)
        out.append({"no": m.no, "place": PLACE.get(m.actor, "학교"), "actor": m.actor, "intent": m.intent,
                    "line": _short_line(sc.line if sc else m.what), "badge": m.badge, "skip": skip,
                    "orphan": "챙길 사람이 없어요" in m.why, "trip": _trip(m.why)})
        skip = 0
    return out


def html(run: AgentRun, scenario_name: str = "") -> str:
    cells = []
    for p in panels(run, scenario_name):
        emoji, color = _face(p["actor"])
        label, scolor = STAMP.get(p["badge"], ("", ""))
        if p.get("orphan") and p["badge"] != "흘러감":
            label = "⚠ 침해 · 방치됨"
        if p.get("trip"):
            label, scolor = f"🔁 {p['trip']}번째 창구", "#e67e22"
        cls = "cm blk" if p["badge"] == "차단" else ("cm end" if p["intent"] in FINAL else "cm")
        stamp = (f'<div class="stamp" style="color:{scolor};border-color:{scolor}">{label}</div>' if label else
                 '<div class="stamp" style="color:#1f8a4c;border-color:#1f8a4c">THE END</div>' if p["intent"] in FINAL
                 else "")
        skip = f' <span style="opacity:.6;font-weight:600">· 앞서 {p["skip"]}장면 생략</span>' if p["skip"] else ""
        name = NODE.get(p["actor"], (None, None, p["actor"]))[2]
        cells.append(
            f'<div class="{cls}"><div class="no">#{p["no"]}{skip}</div><div class="pl">📍 {escape(p["place"])}</div>'
            f'<div class="bub">{escape(p["line"])}</div>'
            f'<div class="who"><div class="face" style="border-color:{color};background:{color}22">{emoji}</div>'
            f'<div class="nm">{escape(name)}</div></div>{stamp}</div>')
    return f'<div class="cm-grid">{"".join(cells)}</div>'
