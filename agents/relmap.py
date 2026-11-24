"""구조별 '인물관계도' (드라마 인물관계도처럼 주체와 관계를 한 장의 SVG로).

선생님을 가운데 두고, 누가 누구를 돕고(초록), 누가 갈등을 만들고(빨강), 누가 위에서 이끄는지(보라),
선생님이 직접 찾아다녀야 하는 곳(주황 점선), 법에 막히는 행동(빨강 점선 ✕)을 화살표로 그린다.
실행 결과가 있으면 인물마다 몇 번 움직였는지 적고, 한 번도 안 나온 인물은 흐리게 한다.
"""
from __future__ import annotations

from html import escape

from .runner import AgentRun

# 무리별 색과 이모지
GROUP = {"me": "#2a6fdb", "opp": "#d64541", "school": "#7f8c8d", "bureau": "#8b5cf6", "org": "#16a085",
         "agent": "#e67e22", "kid": "#e84393"}
NODE = {  # 역할 → (무리, 이모지, 짧은 이름)
    "피해 교원": ("me", "👩‍🏫", "선생님"), "학부모": ("opp", "😠", "학부모"), "학교장": ("school", "🏫", "교장"),
    "교권보호 119": ("bureau", "📞", "교권보호 119"), "상근 전담관": ("bureau", "🧑‍💼", "상근 전담관"),
    "비상근 전담관(법률)": ("bureau", "⚖️", "변호사 전담관"), "비상근 전담관(상담)": ("bureau", "💬", "상담 전담관"),
    "교육감": ("bureau", "🏛️", "교육감(단장)"), "지역교권보호위원회": ("org", "🗂️", "교권보호위원회"),
    "수사기관": ("org", "🚓", "경찰·수사기관"), "지역교권보호지원센터": ("org", "🏢", "지원센터"),
    "교육지원청 담당자": ("org", "📑", "교육지원청"), "교권보호국 요원": ("agent", "🕶️", "교권보호국 요원"),
    # 학생은 에이전트가 아니라 사건 속 인물이다 (점선 동그라미, 움직임 횟수 없음)
    "학생 A": ("kid", "🧒", "학생 A"), "학생 B": ("kid", "👦", "학생 B"), "반 친구들": ("kid", "👫", "반 친구들"),
}
STUDENTS = ("학생 A", "학생 B", "반 친구들")
SUB = {"학생 A": "학부모 자녀", "학생 B": "상대 학생", "반 친구들": "목격자"}
EDGE = {  # 종류 → (색, 점선, 굵기)
    "conflict": ("#d64541", "", 2.6), "help": ("#1f8a4c", "", 2.4), "lead": ("#8b5cf6", "", 2.2),
    "trip": ("#e67e22", "7 5", 2.2), "blocked": ("#d64541", "4 4", 2.0), "plain": ("#95a5a6", "", 1.6),
    "family": ("#e84393", "2 4", 2.2), "none": ("#95a5a6", "2 6", 1.8),
    "covert": ("#4a5a85", "1 5", 2.8),   # 비밀 업무 (점점이 이어진 짙은 선)
}

# 구조별 배치와 관계 (x, y는 640×560 캔버스, 아래쪽 띠에 학생들)
_KIDS = {"학생 A": (75, 430), "학생 B": (240, 470), "반 친구들": (390, 490)}
_KID_EDGES = [("학부모", "학생 A", "family", "내 아이"), ("학생 A", "학생 B", "conflict", "다툼"),
              ("반 친구들", "학교장", "plain", "목격 진술"), ("학교장", "학생 B", "plain", "의견서 받기")]
LAYOUT = {
    "integrated": {
        "pos": {"학부모": (70, 230), "피해 교원": (225, 230), "학교장": (330, 380), "교권보호 119": (225, 60),
                "상근 전담관": (420, 230), "교육감": (420, 60), "비상근 전담관(법률)": (575, 140),
                "비상근 전담관(상담)": (575, 300), "지역교권보호위원회": (465, 410), "수사기관": (575, 45),
                "교육지원청 담당자": (590, 410), **_KIDS},
        "edges": [("학부모", "피해 교원", "conflict", "민원·폭언"), ("피해 교원", "교권보호 119", "help", "한 번만 신고"),
                  ("교권보호 119", "상근 전담관", "help", "배정"), ("상근 전담관", "피해 교원", "help", "1:1 끝까지"),
                  ("교육감", "상근 전담관", "lead", "단장"), ("상근 전담관", "비상근 전담관(법률)", "help", "연결"),
                  ("상근 전담관", "비상근 전담관(상담)", "help", "연결"),
                  ("상근 전담관", "지역교권보호위원회", "help", "심의 요청"), ("교육감", "수사기관", "lead", "고발"),
                  ("교육지원청 담당자", "지역교권보호위원회", "plain", "조사"),
                  ("상근 전담관", "학생 A", "none", "학생은 안 만남"),
                  ("피해 교원", "학생 A", "help", "다툼 중재"), ("학교장", "학생 A", "plain", "분리조치"), *_KID_EDGES],
        "note": "전담관 한 명이 가운데서 전문가와 기관을 묶어 줘요.",
    },
    "distributed": {
        "pos": {"학부모": (70, 230), "피해 교원": (250, 230), "학교장": (330, 380), "지역교권보호지원센터": (470, 60),
                "교육지원청 담당자": (575, 210), "지역교권보호위원회": (560, 390), "수사기관": (70, 60), **_KIDS},
        "edges": [("학부모", "피해 교원", "conflict", "민원·폭언"), ("피해 교원", "학교장", "trip", "① 찾아감"),
                  ("피해 교원", "지역교권보호지원센터", "trip", "② 처음부터 설명"),
                  ("피해 교원", "교육지원청 담당자", "trip", "③ 또 설명"),
                  ("피해 교원", "지역교권보호위원회", "trip", "④ 직접 신청"), ("학부모", "수사기관", "plain", "신고·소송"),
                  ("피해 교원", "학생 A", "help", "다툼 중재"), ("학교장", "학생 A", "plain", "분리조치"), *_KID_EDGES],
        "note": "기관끼리는 서로 연결이 없어서, 선생님이 혼자 여기저기 찾아다녀요.",
    },
    "drama": {  # 요원을 가운데 두고 학생 쪽으로 뻗는 선(막힘)을 부채꼴로
        "pos": {"학부모": (55, 290), "피해 교원": (205, 75), "교권보호국 요원": (350, 245), "학교장": (45, 500),
                "교육감": (500, 60), "수사기관": (595, 190), "지역교권보호위원회": (590, 400),
                "학생 A": (165, 455), "학생 B": (320, 485), "반 친구들": (470, 470)},
        "edges": [("학부모", "피해 교원", "conflict", "민원·폭언"), ("피해 교원", "교권보호국 요원", "help", "출동 요청"),
                  ("교권보호국 요원", "학부모", "blocked", "강제 제지 ✕"),
                  ("교권보호국 요원", "지역교권보호위원회", "blocked", "직접 판정 ✕"),
                  ("교육감", "수사기관", "lead", "고발 (대신 가능)"), ("교육감", "교권보호국 요원", "lead", "지휘"),
                  ("교권보호국 요원", "반 친구들", "covert", "🕵 몰래 정보 캐기 ✕", .4),
                  ("교권보호국 요원", "학생 B", "blocked", "위압 훈계 ✕", .72),
                  ("교권보호국 요원", "학생 A", "covert", "🕵 몰래 SNS·동선 추적 ✕", .45),
                  ("교권보호국 요원", "학부모", "covert", "🕵 잠복·미행 ✕", .5, -.25),
                  ("피해 교원", "학생 A", "help", "다툼 중재", .82), ("학교장", "학생 A", "plain", "분리조치"),
                  *_KID_EDGES[:2]],
        "note": "요원이 대놓고 밀어붙이든 몰래 뒤를 캐든(🕵) 모두 법에 막히고(✕), 교육감 고발 같은 공식 경로만 남아요.",
    },
}
LEGEND = [("help", "도움·연결"), ("conflict", "갈등"), ("lead", "지휘·공식 권한"), ("trip", "선생님이 직접 찾아감"),
          ("blocked", "법에 막힘"), ("family", "가족"), ("none", "직접 닿지 않음"), ("covert", "🕵 비밀 업무 (막힘)")]
R = 28


def _shorten(p, q):
    """두 동그라미 가장자리까지 줄인다. 아래쪽으로 나가는 끝은 이름표를 피해 더 띄운다."""
    (x1, y1), (x2, y2) = p, q
    dx, dy = x2 - x1, y2 - y1
    d = max((dx * dx + dy * dy) ** .5, 1)
    ux, uy = dx / d, dy / d
    r1 = R + (26 if uy > .45 else 6)    # p 아래 이름표 쪽으로 나감
    r2 = R + (26 if uy < -.45 else 8)   # q 아래쪽에서 들어옴
    return (x1 + ux * r1, y1 + uy * r1), (x2 - ux * r2, y2 - uy * r2)


def svg(structure: str, run: AgentRun | None = None) -> str:
    L = LAYOUT[structure]
    pos = L["pos"]
    counts = {}
    if run:
        for t in run.turns:
            counts[t.actor] = counts.get(t.actor, 0) + 1
    out = ['<svg viewBox="0 0 640 560" width="100%" xmlns="http://www.w3.org/2000/svg" '
           'style="font-family: inherit; max-width: 760px; display: block; margin: 0 auto;">', "<defs>"]
    for k, (c, _, _) in EDGE.items():
        out.append(f'<marker id="ar-{structure}-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
                   f'markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
    out.append("</defs>")
    labels = []
    for a, b, kind, label, *opt in L["edges"]:
        t = opt[0] if opt else .5   # 이름표 위치 (선을 따라 0~1)
        bend = opt[1] if len(opt) > 1 else .12   # 휘는 정도 (음수면 반대쪽)
        if a not in pos or b not in pos:
            continue
        c, dash, w = EDGE[kind]
        (x1, y1), (x2, y2) = _shorten(pos[a], pos[b])
        # 살짝 휜 곡선 (인물관계도 느낌)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        nx, ny = -(y2 - y1) * bend, (x2 - x1) * bend
        cx, cy = mx + nx, my + ny
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(f'<path d="M{x1:.0f},{y1:.0f} Q{cx:.0f},{cy:.0f} {x2:.0f},{y2:.0f}" fill="none" stroke="{c}" '
                   f'stroke-width="{w}"{dash_attr} marker-end="url(#ar-{structure}-{kind})" opacity=".9"/>')
        lx = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * cx + t * t * x2
        ly = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * cy + t * t * y2
        tw = len(label) * 11 + 12
        labels.append(f'<rect x="{lx - tw / 2:.0f}" y="{ly - 10:.0f}" width="{tw}" height="20" rx="10" '
                      f'fill="#ffffff" fill-opacity=".92" stroke="{c}" stroke-width="1"/>'
                      f'<text x="{lx:.0f}" y="{ly + 4:.0f}" text-anchor="middle" font-size="11.5" font-weight="600" '
                      f'fill="{c}">{escape(label)}</text>')
    for role, (x, y) in pos.items():
        g, emoji, name = NODE[role]
        c = GROUP[g]
        kid = role in STUDENTS
        kdash = ' stroke-dasharray="5 4"' if kid else ""
        faded = run is not None and not kid and role not in counts
        op = ".35" if faded else "1"
        big = role == "피해 교원"
        r = R + 6 if big else R
        out.append(f'<g opacity="{op}"><circle cx="{x}" cy="{y}" r="{r}" fill="{c}" fill-opacity=".14" stroke="{c}" '
                   f'stroke-width="{3 if big else 2}"{kdash}/>'
                   f'<text x="{x}" y="{y + 8}" text-anchor="middle" font-size="{24 if big else 21}">{emoji}</text>'
                   f'<text x="{x}" y="{y + r + 15}" text-anchor="middle" font-size="12.5" font-weight="700" '
                   f'fill="currentColor">{escape(name)}</text>')
        if role in SUB:
            out.append(f'<text x="{x}" y="{y + r + 29}" text-anchor="middle" font-size="10.5" fill="{c}">'
                       f'{SUB[role]}</text>')
        if run is not None and counts.get(role):
            out.append(f'<circle cx="{x + r - 4}" cy="{y - r + 4}" r="10" fill="{c}"/>'
                       f'<text x="{x + r - 4}" y="{y - r + 8}" text-anchor="middle" font-size="11" font-weight="700" '
                       f'fill="#fff">{counts[role]}</text>')
        out.append("</g>")
    out += labels
    out.append("</svg>")
    return "".join(out)


def legend_html() -> str:
    items = []
    for k, name in LEGEND:
        c, dash, _ = EDGE[k]
        style = f"border-top: 2.5px {'dashed' if dash else 'solid'} {c};"
        items.append(f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;">'
                     f'<span style="display:inline-block;width:26px;{style}"></span>{name}</span>')
    return f'<div style="font-size:.82rem;opacity:.8;margin:4px 0 2px;">{"".join(items)}</div>'


def note(structure: str) -> str:
    return LAYOUT[structure]["note"]
