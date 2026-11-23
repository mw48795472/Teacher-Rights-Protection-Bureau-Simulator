"""에이전트가 주고받는 구조화 데이터."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal[
    "민원제기", "아동학대신고", "소송제기", "폭언·위협",
    "지원요청", "사안접수", "초기상담", "지원계획수립", "전문가연계",
    "법률자문", "심리상담", "갈등조정", "행정절차처리",
    "사실조사", "침해여부판정", "위원회심의요청", "위원회심의·조치",
    "수사기관고발", "수사착수", "현장출동", "물리적제지", "학부모면담", "분리조치",
    "의견서제출", "사안조사", "참고인진술", "분쟁조정신청", "분쟁조정",
    "사후관리", "사안종결", "기타",
]

INTENTS: tuple[str, ...] = Intent.__args__  # type: ignore[attr-defined]


class Action(BaseModel):
    """행위자 에이전트가 제안하는 다음 행동 하나."""
    intent: Intent = Field(description="행동 유형")
    description: str = Field(description="구체적으로 무엇을 하는지 한두 문장")
    target: str = Field(description="행동의 상대방 (사람이나 기관), 없으면 빈 문자열")
    notify: list[str] = Field(description="이 행동 뒤에 움직여야 할 역할 이름들 (주어진 목록에서만)")
    rationale: str = Field(description="이 행동을 고른 이유 한 문장")


Decision = Literal["허용", "조건부 허용", "차단"]
Category = Literal["적법", "권한 초과", "절차 위반", "교육활동 침해 해당", "근거 불충분"]
Trigger = Literal["위원회", "수사기관", "교육감", "보호조치"]


class Verdict(BaseModel):
    """컴플라이언스 에이전트의 판정."""
    decision: Decision
    category: Category
    cited_ids: list[str] = Field(description="근거로 쓴 자료 id (주어진 자료 목록에서만)")
    reason: str = Field(description="판정 이유. 근거 조문 내용을 짚어 2~3문장")
    condition: str = Field(description="조건부 허용일 때 지켜야 할 조건, 아니면 빈 문자열")
    alternative_intent: str = Field(description="차단할 때 대신 해야 할 행동 유형, 없으면 빈 문자열")
    alternative_actor: str = Field(description="대안 행동을 할 역할 이름, 없으면 빈 문자열")
    triggers: list[Trigger] = Field(description="이 행동 때문에 시작돼야 하는 후속 절차")
