"""Server operations bearer or DB-checked account editor authorization."""

import hmac
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.runtime import Runtime
from api.store import StoreError

account_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="AccountBearer",
    description="Account access token with a server-verified editor/admin role.",
)


def editorial_dependency(
    settings,
    runtime_dependency,
    principal_dependency,
    operations_security,
    *,
    legacy_operations=False,
):
    runtime = Annotated[Runtime, Depends(runtime_dependency)]

    def editor(
        request: Request,
        rt: runtime,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(operations_security)],
        account_credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(account_bearer)
        ],
    ):
        expected = settings.operations_token.get_secret_value()
        if credentials is not None and credentials.scheme.lower() == "bearer":
            if expected and hmac.compare_digest(
                credentials.credentials.encode(), expected.encode()
            ):
                return "operations"
            try:
                principal = principal_dependency(request, credentials)
            except StoreError as error:
                if legacy_operations and not expected and error.status == 401:
                    raise StoreError(
                        503, "operations_unavailable", "Operations access is not configured"
                    ) from None
                raise
            if legacy_operations and not getattr(principal, "account_id", None):
                if not expected:
                    raise StoreError(
                        503, "operations_unavailable", "Operations access is not configured"
                    )
                raise StoreError(
                    401, "operations_authentication_required", "Operations token required"
                )
            from api.accounts import require_role

            account = require_role(rt, principal, allowed={"editor", "admin"})
            return str(account.id)
        if legacy_operations and not expected:
            raise StoreError(503, "operations_unavailable", "Operations access is not configured")
        raise StoreError(401, "authentication_required", "Editor authentication required")

    return editor
