"""Typed response failures with diagnostic metadata, never SDK request/error bodies."""

DIAGNOSTIC_KEYS = {
    "finish_reason",
    "block_reason",
    "response_has_text",
    "error_code",
    "max_output_tokens",
    "provider_status_code",
    "provider_reason",
    "error_category",
    "retryable",
    "role",
}

PROVIDER_REASONS = {
    "API_KEY_INVALID",
    "API_KEY_EXPIRED",
    "API_KEY_SERVICE_BLOCKED",
    "API_KEY_HTTP_REFERRER_BLOCKED",
    "API_KEY_IP_ADDRESS_BLOCKED",
    "BILLING_DISABLED",
    "CONSUMER_INVALID",
    "SERVICE_DISABLED",
}


def provider_reason(error):
    def find(value):
        if isinstance(value, dict):
            reason = value.get("reason")
            if isinstance(reason, str) and reason in PROVIDER_REASONS:
                return reason
            for child in value.values():
                found = find(child)
                if found:
                    return found
        if isinstance(value, list):
            for child in value:
                found = find(child)
                if found:
                    return found
        return None

    found = find(getattr(error, "response_json", None)) or find(getattr(error, "details", None))
    if not found and "api key not valid" in str(getattr(error, "message", "")).lower():
        found = "API_KEY_INVALID"
    return found


def provider_error_diagnostics(error):
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    if isinstance(status, int) and 100 <= status <= 599:
        result = {"provider_status_code": status, "error_code": "provider_request_failed"}
        reason = provider_reason(error)
        if reason:
            result["provider_reason"] = reason
        return result
    return {}


class ReviewValidationError(ValueError):
    def __init__(self, code, category="review_format"):
        self.error_code, self.category = code, category
        super().__init__(code)


def failure_info(error, role=None):
    cause = error.__cause__
    if isinstance(error, RuntimeError) and cause is not None:
        seen = {id(error)}
        for _ in range(8):
            if id(cause) in seen:
                break
            seen.add(id(cause))
            if not isinstance(cause, RuntimeError) or cause.__cause__ is None:
                return {**failure_info(cause, role), "error_type": type(error).__name__}
            cause = cause.__cause__
    info = {
        "error_type": type(error).__name__,
        "error_code": "internal_error",
        "error_category": "technical",
        "retryable": False,
        **provider_error_diagnostics(error),
    }
    if role:
        info["role"] = role
    if getattr(error, "failures", None):
        info.update(
            {key: value for key, value in error.failures[0].items() if key in DIAGNOSTIC_KEYS}
        )
        return info
    status = info.get("provider_status_code")
    if info.get("provider_reason") in PROVIDER_REASONS or status in {401, 403}:
        info.update(
            error_code="credential_invalid" if status != 403 else "permission_denied",
            error_category="configuration",
        )
    elif status == 404:
        info.update(error_code="model_not_found", error_category="configuration")
    elif status == 429 or status and status >= 500:
        info.update(error_code="provider_unavailable", retryable=True)
    elif isinstance(error, (TimeoutError, ConnectionError)) or type(error).__name__ in {
        "APITimeoutError",
        "APIConnectionError",
        "ConnectTimeout",
        "ReadTimeout",
        "ConnectError",
        "RemoteProtocolError",
    }:
        info.update(error_code="provider_unavailable", retryable=True)
    elif isinstance(error, ReviewValidationError):
        info.update(
            error_code=error.error_code,
            error_category=error.category,
            retryable=error.category == "review_format",
        )
    elif isinstance(error, ModelResponseError):
        info.update(error.diagnostics, retryable=isinstance(error, TruncatedModelResponse))
    return info


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
