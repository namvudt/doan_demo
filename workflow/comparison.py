"""Descriptive comparison only. Independent correctness evaluation is not implemented yet."""

import time
from io import BytesIO

from PIL import Image

from baselines.generic_tool_agent import GenericToolAgentBaseline
from baselines.vanilla_vlm import VanillaVLMBaseline
from core.images import validate_image
from workflow.service import RunService


def compare(image_data, query, llm, audience="tourist"):
    normalized = validate_image(image_data, llm.config)
    image = Image.open(BytesIO(normalized))
    rows = []
    try:
        for cls in (VanillaVLMBaseline, GenericToolAgentBaseline):
            client = llm.for_run(benchmark=True)
            started = time.monotonic()
            row = {
                "method": cls.__name__,
                "answer": None,
                "error_type": None,
                "config_snapshot": client.config.snapshot(),
            }
            try:
                answer, metadata = cls(client).run(image, query)
                row.update(answer=answer, metadata=metadata, status="generated_unverified")
            except Exception as exc:
                row.update(status="failed", error_type=type(exc).__name__)
            finally:
                row.update(duration=time.monotonic() - started, calls=list(client.calls))
                client.close()
            rows.append(row)
        result = RunService(llm, benchmark=True).run(normalized, query, audience)
        rows.append(
            {
                "method": "LangGraph",
                "status": result.status,
                "answer": result.final_response,
                "duration": result.duration,
                "calls": result.calls,
                "run": result.model_dump(mode="json"),
            }
        )
    finally:
        image.close()
    return {
        "evaluation_status": "not_evaluated",
        "verdict": None,
        "limitations": [
            "Chưa có evaluator độc lập hoặc đáp án chuẩn.",
            "Baseline ReAct chỉ là prompt mô phỏng, không thực thi công cụ.",
            "Không suy ra độ chính xác hoặc phương pháp thắng từ bảng này.",
        ],
        "rows": rows,
    }
