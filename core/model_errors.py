"""Typed response failures with diagnostic metadata, never SDK request/error bodies."""

DIAGNOSTIC_KEYS = {
    "finish_reason",
    "block_reason",
    "response_has_text",
    "error_code",
    "max_output_tokens",
    "provider_status_code",
}


def provider_error_diagnostics(error):
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    if isinstance(status, int) and 100 <= status <= 599:
        return {"provider_status_code": status, "error_code": "provider_request_failed"}
    return {}


def enum_name(value):
    if value is None:
        return None
    result = str(getattr(value, "value", value)).rsplit(".", 1)[-1]
    return result if result.replace("_", "").isalnum() and len(result) <= 60 else "UNKNOWN"


def response_diagnostics(record):
    return {
        key: value
        for key, value in record.items()
        if key in DIAGNOSTIC_KEYS and isinstance(value, (str, bool, int))
    }


class ModelResponseError(ValueError):
    code = "invalid_model_response"

    def __init__(self, *, usage=None, finish_reason=None, block_reason=None, text=""):
        self.usage = usage
        self.diagnostics = response_diagnostics(
            {
                "finish_reason": enum_name(finish_reason),
                "block_reason": enum_name(block_reason),
                "response_has_text": bool(text.strip()),
                "error_code": self.code,
            }
        )
        self.partial_response = text
        super().__init__(self.code + ": " + (enum_name(finish_reason) or "UNKNOWN"))


class TruncatedModelResponse(ModelResponseError):
    code = "output_token_limit"


class BlockedModelResponse(ModelResponseError):
    code = "response_blocked"


class EmptyModelResponse(ModelResponseError):
    code = "empty_model_response"


class IncompleteModelResponse(ModelResponseError):
    code = "incomplete_model_response"


def validate_response(text, usage, finish_reason, block_reason=None):
    finish, block = enum_name(finish_reason), enum_name(block_reason)
    options = dict(text=text, usage=usage, finish_reason=finish, block_reason=block)
    if (
        block
        and block
        not in {"BLOCK_REASON_UNSPECIFIED", "BLOCKED_REASON_UNSPECIFIED", "UNSPECIFIED", "0"}
        or finish
        in {
            "SAFETY",
            "RECITATION",
            "BLOCKLIST",
            "PROHIBITED_CONTENT",
            "SPII",
            "IMAGE_SAFETY",
            "content_filter",
        }
    ):
        raise BlockedModelResponse(**options)
    if finish in {"MAX_TOKENS", "length"}:
        raise TruncatedModelResponse(**options)
    if not text.strip():
        raise EmptyModelResponse(**options)
    if finish and finish not in {"STOP", "stop"}:
        raise IncompleteModelResponse(**options)
