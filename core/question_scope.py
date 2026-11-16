"""Deterministic slot boundaries for partial answers without relaxing evidence gates."""

import re
from dataclasses import dataclass

HAN_REQUEST = re.compile(
    r"(?:đọc|dịch|phiên âm|read|translate|transcribe).*(?:hán|nôm|hoành phi|câu đối|han.nom)", re.I
)
CREATIVE_REQUEST = re.compile(r"(?:sáng tác|bài thơ|làm thơ|write a poem|compose a poem)", re.I)
SUPPORTED_REQUEST = re.compile(
    r"(?:mô tả|kiến trúc|nhận diện|xác định|lịch sử|khởi dựng|trùng tu|niên đại|"
    r"vật liệu|công trình nào|ở đâu|chi tiết|bố cục|describe|visible|identify|history|materials)",
    re.I,
)
BOUNDARY = re.compile(r"[;.!?\n]+|\s+(?:và|đồng thời|ngoài ra|nhưng|and|also)\s+", re.I)


@dataclass(frozen=True)
class QuestionScope:
    question: str
    supported_question: str
    limitations: tuple[str, ...]
    out_of_scope: bool


def question_scope(question, *, allow_generation=False, allow_han_nom=False):
    limitations, supported = [], []
    for clause in BOUNDARY.split(question):
        clause = clause.strip(" ,:")
        if not clause:
            continue
        han = HAN_REQUEST.search(clause) if not allow_han_nom else None
        creative = CREATIVE_REQUEST.search(clause) if not allow_generation else None
        if han or creative:
            if han:
                limitations.append(
                    "Phần phiên đọc hoặc dịch chữ Hán–Nôm chưa được hỗ trợ; cần chuyên gia hoặc tư liệu đã được duyệt."
                )
            if creative:
                limitations.append("Phần sáng tác chưa được bật trong cấu hình hiện tại.")
            # Preserve a supported prefix even when a connector is omitted.
            prefix = clause[: min(match.start() for match in (han, creative) if match)].strip(" ,:")
            if SUPPORTED_REQUEST.search(prefix):
                supported.append(prefix)
        elif (
            SUPPORTED_REQUEST.search(clause)
            or (allow_generation and CREATIVE_REQUEST.search(clause))
            or (allow_han_nom and HAN_REQUEST.search(clause))
            or not (HAN_REQUEST.search(question) or CREATIVE_REQUEST.search(question))
        ):
            supported.append(clause)
    limitations = tuple(dict.fromkeys(limitations))
    return QuestionScope(
        question=question,
        supported_question="; ".join(supported) if limitations else question,
        limitations=limitations,
        out_of_scope=bool(limitations and not supported),
    )
