"""Opaque account sessions and server-enforced editorial roles."""

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from api.models import SessionToken
from api.product_models import Account, AccountSession, AuthRateLimit, ProductAudit
from api.product_schemas import (
    AccountView,
    AuthView,
    LoginBody,
    PasswordBody,
    ProfilePatch,
    RefreshBody,
    RegisterBody,
    RoleBody,
)
from api.store import StoreError
from api.views import timestamp

ACCESS_SECONDS = 1800
REFRESH_SECONDS = 30 * 86400


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=16384, r=8, p=1, maxmem=64 * 1024 * 1024
    )
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def password_matches(password, encoded):
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        salt, expected = (
            base64.b64decode(salt, validate=True),
            base64.b64decode(expected, validate=True),
        )
    except (ValueError, TypeError):
        salt, expected = b"0" * 16, b"0" * 64
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=16384, r=8, p=1, maxmem=64 * 1024 * 1024
    )
    return hmac.compare_digest(digest, expected)


def account_view(record):
    return {
        "account_id": record.id,
        "email": record.email,
        "display_name": record.display_name,
        "role": record.role,
        "disabled": record.disabled,
        "version": record.version,
        "created_at": timestamp(record.created_at),
    }


def audit(session, action, target, *, actor=None, metadata=None):
    session.add(
        ProductAudit(
            id=str(uuid4()),
            actor_id=actor,
            action=action,
            target_id=target,
            metadata_json=metadata or {},
            created_at=time.time(),
        )
    )


@dataclass(frozen=True)
class AccountPrincipal:
    # Existing run/asset ownership remains stable across account login devices.
    id: str
    label: str
    expires_at: float
    account_id: str
    account_session_id: str
    roles: tuple[str, ...]


class AccountStore:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings

    def throttle(self, scope, identity, limit, window):
        key = token_hash(scope + ":" + identity)
        with self.db.session() as session:
            if self.db.engine.dialect.name == "postgresql":
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(key[:15], 16)}
                )
            else:
                session.execute(
                    update(AuthRateLimit)
                    .where(AuthRateLimit.key == key)
                    .values(attempts=AuthRateLimit.attempts)
                )
            row = session.get(AuthRateLimit, key)
            now = time.time()
            if row is None:
                session.add(AuthRateLimit(key=key, started_at=now, attempts=1))
            elif now - row.started_at >= window:
                row.started_at, row.attempts = now, 1
            elif row.attempts >= limit:
                raise StoreError(
                    429, "auth_rate_limit", "Too many authentication attempts; retry later"
                )
            else:
                row.attempts += 1

    @staticmethod
    def issue(session, account):
        now = time.time()
        access, refresh = secrets.token_urlsafe(40), secrets.token_urlsafe(48)
        record = AccountSession(
            id=str(uuid4()),
            account_id=account.id,
            token_hash=token_hash(access),
            refresh_hash=token_hash(refresh),
            created_at=now,
            expires_at=now + ACCESS_SECONDS,
            refresh_expires_at=now + REFRESH_SECONDS,
            revoked=False,
        )
        session.add(record)
        return AccountStore.issued_view(account, record, access, refresh)

    @staticmethod
    def issued_view(account, record, access, refresh):
        return {
            "account": account_view(account),
            "session_id": record.id,
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_at": timestamp(record.expires_at),
            "refresh_expires_at": timestamp(record.refresh_expires_at),
        }

    def register(self, body, remote):
        self.throttle("register", remote, 5, 3600)
        encoded = password_hash(body.password)
        try:
            with self.db.session() as session:
                now, owner_id = time.time(), str(uuid4())
                owner = SessionToken(
                    id=owner_id,
                    token_hash=token_hash(secrets.token_urlsafe(64)),
                    label=body.display_name,
                    created_at=now,
                    expires_at=now + 100 * 365 * 86400,
                    last_seen=now,
                    revoked=False,
                )
                session.add(owner)
                session.flush()
                record = Account(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    email=body.email,
                    display_name=body.display_name,
                    password_hash=encoded,
                    role="user",
                    disabled=False,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                session.flush()
                audit(session, "account.register", record.id, actor=record.id)
                return account_view(record)
        except IntegrityError:
            raise StoreError(
                409, "account_exists", "Account registration conflicts with an existing account"
            ) from None

    def login(self, body, remote):
        email = body.email.strip().casefold()
        self.throttle("login-ip", remote, 30, 60)
        self.throttle("login-account", email, 8, 60)
        with self.db.session() as session:
            record = session.scalar(select(Account).where(Account.email == email))
            correct = password_matches(body.password, record.password_hash if record else "")
            if not record or not correct or record.disabled:
                raise StoreError(401, "invalid_credentials", "Email or password is incorrect")
            unchanged = session.execute(
                update(Account)
                .where(
                    Account.id == record.id,
                    Account.password_hash == record.password_hash,
                    Account.disabled.is_(False),
                )
                .values(updated_at=Account.updated_at)
            )
            if not unchanged.rowcount:
                raise StoreError(401, "invalid_credentials", "Email or password is incorrect")
            return self.issue(session, record)

    def refresh(self, token, remote):
        self.throttle("refresh", remote, 60, 60)
        digest, now = token_hash(token), time.time()
        with self.db.session() as session:
            # An update obtains a write lock before reading, preventing two rotations.
            session.execute(
                update(AccountSession)
                .where(AccountSession.refresh_hash == digest)
                .values(created_at=AccountSession.created_at)
            )
            record = session.scalar(
                select(AccountSession).where(AccountSession.refresh_hash == digest)
            )
            account = session.get(Account, record.account_id) if record else None
            if (
                not record
                or record.revoked
                or record.refresh_expires_at <= now
                or not account
                or account.disabled
            ):
                raise StoreError(
                    401, "invalid_refresh_token", "Refresh token is invalid or expired"
                )
            access, refresh = secrets.token_urlsafe(40), secrets.token_urlsafe(48)
            record.token_hash, record.refresh_hash = token_hash(access), token_hash(refresh)
            record.expires_at = now + ACCESS_SECONDS
            # Rotation does not extend the original refresh lifetime indefinitely.
            return self.issued_view(account, record, access, refresh)

    def authenticate(self, token):
        with self.db.session() as session:
            record = session.scalar(
                select(AccountSession).where(AccountSession.token_hash == token_hash(token))
            )
            account = session.get(Account, record.account_id) if record else None
            owner = session.get(SessionToken, account.owner_id) if account else None
            if (
                not record
                or record.revoked
                or record.expires_at <= time.time()
                or not account
                or account.disabled
                or not owner
                or owner.revoked
                or owner.expires_at <= time.time()
            ):
                raise StoreError(401, "invalid_token", "Session token is invalid or expired")
            return AccountPrincipal(
                owner.id,
                account.display_name,
                record.expires_at,
                account.id,
                record.id,
                (account.role,),
            )

    def revoke_current(self, principal):
        identifier = getattr(principal, "account_session_id", None)
        if identifier is None:
            return False
        with self.db.session() as session:
            session.execute(
                update(AccountSession).where(AccountSession.id == identifier).values(revoked=True)
            )
        return True

    def me(self, principal):
        with self.db.session() as session:
            return account_view(require_account(session, principal))

    def patch(self, principal, body):
        with self.db.session() as session:
            record = require_account(session, principal)
            changed = session.execute(
                update(Account)
                .where(Account.id == record.id, Account.version == body.version)
                .values(
                    display_name=body.display_name, version=body.version + 1, updated_at=time.time()
                )
            )
            if not changed.rowcount:
                raise StoreError(
                    409, "account_version_conflict", "Reload the current profile before editing"
                )
            session.execute(
                update(SessionToken)
                .where(SessionToken.id == record.owner_id)
                .values(label=body.display_name)
            )
            record = session.get(Account, record.id, populate_existing=True)
            return account_view(record)

    def password(self, principal, body):
        with self.db.session() as session:
            session.execute(
                update(Account)
                .where(Account.id == getattr(principal, "account_id", None))
                .values(version=Account.version)
            )
            record = require_account(session, principal)
            if not password_matches(body.current_password, record.password_hash):
                raise StoreError(401, "invalid_credentials", "Current password is incorrect")
            record.password_hash = password_hash(body.new_password)
            record.updated_at, record.version = time.time(), record.version + 1
            session.execute(
                update(AccountSession)
                .where(AccountSession.account_id == record.id)
                .values(revoked=True)
            )
            audit(session, "account.password_change", record.id, actor=record.id)

    def role(self, identifier, body, *, reason=None, actor="operations"):
        with self.db.session() as session:
            record = session.get(Account, str(identifier))
            if not record:
                raise StoreError(404, "account_not_found", "Account was not found")
            changed = session.execute(
                update(Account)
                .where(Account.id == record.id, Account.version == body.version)
                .values(
                    role=body.role,
                    disabled=body.disabled,
                    version=body.version + 1,
                    updated_at=time.time(),
                )
            )
            if not changed.rowcount:
                raise StoreError(
                    409, "account_version_conflict", "Reload the current account before editing"
                )
            session.execute(
                update(SessionToken)
                .where(SessionToken.id == record.owner_id)
                .values(revoked=body.disabled)
            )
            if body.disabled:
                session.execute(
                    update(AccountSession)
                    .where(AccountSession.account_id == record.id)
                    .values(revoked=True)
                )
            audit(
                session,
                "account.role_change",
                record.id,
                actor=actor,
                metadata={
                    "role": body.role,
                    "disabled": body.disabled,
                    **({"reason": reason} if reason else {}),
                },
            )
            return account_view(session.get(Account, record.id, populate_existing=True))


def require_account(session, principal):
    identifier = getattr(principal, "account_id", None)
    record = session.get(Account, identifier) if identifier else None
    if not record or record.disabled or record.owner_id != principal.id:
        raise StoreError(403, "account_required", "A signed-in account is required")
    return record


def require_role(rt, principal, allowed=("editor", "admin")):
    with rt.db.session() as session:
        record = require_account(session, principal)
        if record.role not in allowed:
            raise StoreError(403, "role_required", "This operation requires an editorial role")
        return record


def principal_active(database, principal):
    if not getattr(principal, "account_session_id", None):
        return None
    with database.session() as session:
        record = session.get(AccountSession, principal.account_session_id)
        account = session.get(Account, principal.account_id)
        stable_owner = session.get(SessionToken, principal.id)
        return bool(
            record
            and record.account_id == principal.account_id
            and not record.revoked
            and record.expires_at > time.time()
            and account
            and not account.disabled
            and stable_owner
            and not stable_owner.revoked
            and stable_owner.expires_at > time.time()
        )


def account_router(settings, *, runtime_dependency, principal_dependency, operations_security):
    router = APIRouter(prefix="/api/v1", tags=["Accounts"])
    runtime = Annotated[object, Depends(runtime_dependency)]
    owner = Annotated[object, Depends(principal_dependency)]
    account_security = HTTPBearer(auto_error=False, scheme_name="AccountBearer")

    def operations(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(operations_security)],
        account_credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(account_security)
        ],
        rt: runtime,
    ):
        expected = settings.operations_token.get_secret_value()
        if (
            credentials
            and expected
            and hmac.compare_digest(credentials.credentials.encode(), expected.encode())
        ):
            return "operations"
        if account_credentials is None:
            raise StoreError(
                401,
                "authentication_required",
                "An administrator account or operations token is required",
            )
        principal = rt.store.authenticate(account_credentials.credentials)
        return require_role(rt, principal, allowed=("admin",)).id

    def remote(request):
        return request.client.host if request.client else "unknown"

    @router.post("/accounts", response_model=AccountView, status_code=201)
    def register(body: RegisterBody, request: Request, rt: runtime):
        return AccountStore(rt.db, settings).register(body, remote(request))

    @router.post("/auth/sessions", response_model=AuthView)
    def login(body: LoginBody, request: Request, rt: runtime, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return AccountStore(rt.db, settings).login(body, remote(request))

    @router.post("/auth/refresh", response_model=AuthView)
    def refresh(body: RefreshBody, request: Request, rt: runtime, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return AccountStore(rt.db, settings).refresh(body.refresh_token, remote(request))

    @router.delete("/auth/sessions/current", status_code=204)
    def logout(principal: owner, rt: runtime):
        if not AccountStore(rt.db, settings).revoke_current(principal):
            raise StoreError(403, "account_required", "A signed-in account is required")
        return Response(status_code=204)

    @router.get("/users/me", response_model=AccountView)
    def me(principal: owner, rt: runtime):
        return AccountStore(rt.db, settings).me(principal)

    @router.patch("/users/me", response_model=AccountView)
    def patch(body: ProfilePatch, principal: owner, rt: runtime):
        return AccountStore(rt.db, settings).patch(principal, body)

    @router.post("/users/me/password", status_code=204)
    def password(body: PasswordBody, principal: owner, rt: runtime):
        AccountStore(rt.db, settings).password(principal, body)
        return Response(status_code=204)

    @router.put(
        "/operations/accounts/{account_id}/role",
        response_model=AccountView,
    )
    def role(
        account_id: UUID, body: RoleBody, rt: runtime, actor: Annotated[str, Depends(operations)]
    ):
        return AccountStore(rt.db, settings).role(account_id, body, actor=actor)

    return router
