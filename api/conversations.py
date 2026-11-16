"""Owned conversation turns and bounded, explicitly unverified memory."""

import time
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, func, select, update

from api.accounts import require_account
from api.catalog_store import catalog_views
from api.models import HeritageSite, Run
from api.product_models import (
    Account,
    Conversation,
    ConversationMessage,
    ConversationTurn,
    HeritageFavorite,
)
from api.product_schemas import (
    ConversationCreate,
    ConversationPage,
    ConversationPatch,
    ConversationView,
    FavoritePage,
    FavoriteView,
    MessagePage,
)
from api.store import ACTIVE, StoreError
from api.views import timestamp


def visible_run():
    column = getattr(Run, "deleted_at", None)
    return column.is_(None) if column is not None else True


def conversation_record(session, identifier, owner):
    record = session.get(Conversation, str(identifier))
    if record is None or record.owner_id != owner:
        raise StoreError(404, "conversation_not_found", "Conversation was not found")
    return record


def conversation_view(record):
    return {
        "conversation_id": record.id,
        "title": record.title,
        "memory_enabled": record.memory_enabled,
        "archived": record.archived,
        "version": record.version,
        "created_at": timestamp(record.created_at),
        "updated_at": timestamp(record.updated_at),
    }


def memory_snapshot(session, record):
    if not record.memory_enabled:
        return []
    rows = session.execute(
        select(ConversationMessage, ConversationTurn.run_id)
        .join(ConversationTurn, ConversationTurn.id == ConversationMessage.turn_id)
        .join(Run, Run.id == ConversationTurn.run_id)
        .where(
            ConversationTurn.conversation_id == record.id,
            ConversationTurn.created_at > record.memory_cleared_at,
            Run.execution_status.in_(["succeeded", "awaiting_input"]),
            visible_run(),
        )
        .order_by(ConversationTurn.position.desc(), ConversationMessage.created_at.desc())
        .limit(8)
    ).all()
    result, remaining = [], 4000
    for message, run_id in rows:
        text = message.content[: min(1000, remaining)]
        if not text:
            continue
        result.append(
            {
                "role": message.role,
                "content": text,
                "run_id": run_id,
                "provenance": message.provenance,
                "unverified_context": True,
            }
        )
        remaining -= len(text)
        if not remaining:
            break
    return list(reversed(result))


def bind_conversation_run(session, owner, body, run):
    identifier = getattr(body, "conversation_id", None)
    parent_turn = (
        session.scalar(
            select(ConversationTurn).where(ConversationTurn.run_id == str(body.parent_run_id))
        )
        if body.parent_run_id
        else None
    )
    if identifier and parent_turn and str(identifier) != parent_turn.conversation_id:
        raise StoreError(
            409,
            "conversation_parent_conflict",
            "A child run must remain in its parent conversation",
        )
    identifier = identifier or (parent_turn.conversation_id if parent_turn else None)
    if not identifier:
        return
    record = conversation_record(session, identifier, owner)
    if record.archived:
        raise StoreError(
            409, "conversation_archived", "Restore this conversation before adding a turn"
        )
    if record.memory_enabled and session.scalar(
        select(Run.id)
        .join(ConversationTurn, ConversationTurn.run_id == Run.id)
        .where(
            ConversationTurn.conversation_id == record.id,
            Run.execution_status.in_(ACTIVE),
            visible_run(),
        )
        .limit(1)
    ):
        raise StoreError(
            409,
            "conversation_busy",
            "Wait for the active turn before using conversation memory",
        )
    # Store.create_run already holds the stable owner writer lock.
    snapshot = memory_snapshot(session, record)
    run.input_context = {
        **(run.input_context or {}),
        "conversation_id": record.id,
        "conversation_memory": snapshot,
        "memory_policy": {"max_messages": 8, "max_characters": 4000, "unverified_context": True},
    }
    now, turn_id = time.time(), str(uuid4())
    turn = ConversationTurn(
        id=turn_id,
        conversation_id=record.id,
        run_id=run.id,
        position=record.next_turn,
        created_at=now,
    )
    record.next_turn += 1
    record.updated_at = now
    session.add(turn)
    session.flush()
    user_text = (
        (run.input_context or {}).get("answer")
        or (run.input_context or {}).get("selected_candidate")
        or run.question
    )
    session.add(
        ConversationMessage(
            id=str(uuid4()),
            turn_id=turn_id,
            role="user",
            content=user_text,
            provenance={
                "kind": "user_input",
                "run_id": run.id,
                "run_kind": run.run_kind,
                "verified": False,
            },
            created_at=now,
        )
    )


def sync_conversation_result(session, run):
    """Worker persistence hook: store only the public final response, never a draft."""
    turn = session.scalar(select(ConversationTurn).where(ConversationTurn.run_id == run.id))
    if not turn or getattr(run, "deleted_at", None) is not None:
        return
    content = (run.result or {}).get("final_response")
    if run.execution_status not in {"succeeded", "awaiting_input"} or not content:
        return
    existing = session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.turn_id == turn.id, ConversationMessage.role == "assistant"
        )
    )
    if existing:
        return
    result = run.result or {}
    cited = (result.get("judge_report") or {}).get("cited_source_ids", [])
    session.add(
        ConversationMessage(
            id=str(uuid4()),
            turn_id=turn.id,
            role="assistant",
            content=content[:50000],
            created_at=time.time(),
            provenance={
                "kind": "model_output",
                "run_id": run.id,
                "source_ids": cited[:100],
                "verification_status": "automatic_review",
                "verified": False,
            },
        )
    )


def purge_run_dependencies(session, identifiers):
    turns = select(ConversationTurn.id).where(ConversationTurn.run_id.in_(identifiers))
    session.execute(delete(ConversationMessage).where(ConversationMessage.turn_id.in_(turns)))
    session.execute(delete(ConversationTurn).where(ConversationTurn.run_id.in_(identifiers)))


def purge_owner_dependencies(session, identifiers):
    if session.scalar(select(Account.id).where(Account.owner_id.in_(identifiers)).limit(1)):
        raise StoreError(
            409,
            "account_owner_protected",
            "Account principals require an explicit account deletion workflow",
        )
    conversations = select(Conversation.id).where(Conversation.owner_id.in_(identifiers))
    turns = select(ConversationTurn.id).where(ConversationTurn.conversation_id.in_(conversations))
    session.execute(delete(ConversationMessage).where(ConversationMessage.turn_id.in_(turns)))
    session.execute(
        delete(ConversationTurn).where(ConversationTurn.conversation_id.in_(conversations))
    )
    session.execute(delete(Conversation).where(Conversation.owner_id.in_(identifiers)))
    session.execute(delete(HeritageFavorite).where(HeritageFavorite.owner_id.in_(identifiers)))


class ConversationStore:
    def __init__(self, database):
        self.db = database

    def create(self, owner, body):
        now = time.time()
        record = Conversation(
            id=str(uuid4()),
            owner_id=owner,
            title=body.title.strip() or "Hội thoại mới",
            memory_enabled=body.memory_enabled,
            memory_cleared_at=0,
            archived=False,
            version=1,
            next_turn=1,
            created_at=now,
            updated_at=now,
        )
        with self.db.session() as session:
            session.add(record)
        return conversation_view(record)

    def list(self, owner, limit, offset):
        with self.db.session() as session:
            condition = Conversation.owner_id == owner
            total = session.scalar(select(func.count()).select_from(Conversation).where(condition))
            records = session.scalars(
                select(Conversation)
                .where(condition)
                .order_by(Conversation.updated_at.desc(), Conversation.id)
                .limit(limit)
                .offset(offset)
            )
            return {
                "items": [conversation_view(record) for record in records],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def get(self, owner, identifier):
        with self.db.session() as session:
            return conversation_view(conversation_record(session, identifier, owner))

    def patch(self, owner, identifier, body):
        with self.db.session() as session:
            record = conversation_record(session, identifier, owner)
            values = body.model_dump(exclude={"version"}, exclude_none=True)
            if "title" in values:
                if not values["title"].strip():
                    raise StoreError(
                        422, "conversation_title_required", "Conversation title is required"
                    )
                values["title"] = values["title"].strip()
            changed = session.execute(
                update(Conversation)
                .where(Conversation.id == record.id, Conversation.version == body.version)
                .values(**values, version=body.version + 1, updated_at=time.time())
            )
            if not changed.rowcount:
                raise StoreError(
                    409, "conversation_version_conflict", "Reload this conversation before editing"
                )
            return conversation_view(session.get(Conversation, record.id, populate_existing=True))

    def messages(self, owner, identifier, limit, offset):
        with self.db.session() as session:
            record = conversation_record(session, identifier, owner)
            condition = [ConversationTurn.conversation_id == record.id, visible_run()]
            query = (
                select(ConversationMessage, ConversationTurn)
                .join(ConversationTurn, ConversationTurn.id == ConversationMessage.turn_id)
                .join(Run, Run.id == ConversationTurn.run_id)
                .where(*condition)
            )
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.execute(
                query.order_by(
                    ConversationTurn.position,
                    ConversationMessage.created_at,
                    ConversationMessage.id,
                )
                .limit(limit)
                .offset(offset)
            ).all()
            return {
                "items": [
                    {
                        "message_id": message.id,
                        "turn_id": turn.id,
                        "run_id": turn.run_id,
                        "position": turn.position,
                        "role": message.role,
                        "content": message.content,
                        "provenance": message.provenance,
                        "created_at": timestamp(message.created_at),
                    }
                    for message, turn in rows
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def memory(self, owner, identifier):
        with self.db.session() as session:
            record = conversation_record(session, identifier, owner)
            return {
                "conversation_id": record.id,
                "enabled": record.memory_enabled,
                "items": memory_snapshot(session, record),
                "unverified_context": True,
                "max_messages": 8,
                "max_characters": 4000,
            }

    def clear_memory(self, owner, identifier):
        with self.db.session() as session:
            record = conversation_record(session, identifier, owner)
            record.memory_cleared_at = record.updated_at = time.time()
            record.version += 1

    def delete(self, owner, identifier):
        with self.db.session() as session:
            record = conversation_record(session, identifier, owner)
            runs = select(ConversationTurn.run_id).where(
                ConversationTurn.conversation_id == record.id
            )
            if session.scalar(
                select(Run.id).where(Run.id.in_(runs), Run.execution_status.in_(ACTIVE)).limit(1)
            ):
                raise StoreError(
                    409,
                    "conversation_active",
                    "Wait for active runs before removing this conversation",
                )
            turns = select(ConversationTurn.id).where(ConversationTurn.conversation_id == record.id)
            session.execute(
                delete(ConversationMessage).where(ConversationMessage.turn_id.in_(turns))
            )
            session.execute(
                delete(ConversationTurn).where(ConversationTurn.conversation_id == record.id)
            )
            session.delete(record)

    def favorite(self, principal, heritage_id, saved):
        with self.db.session() as session:
            require_account(session, principal)
            heritage = session.get(HeritageSite, heritage_id)
            if heritage is None or heritage.content_status != "published":
                raise StoreError(404, "heritage_not_found", "Heritage was not found")
            # Owner lock makes repeated PUT safe without swallowing unrelated errors.
            from api.models import SessionToken

            session.execute(
                update(SessionToken)
                .where(SessionToken.id == principal.id)
                .values(last_seen=time.time())
            )
            record = session.get(HeritageFavorite, (principal.id, heritage_id))
            if saved and record is None:
                record = HeritageFavorite(
                    owner_id=principal.id, heritage_id=heritage_id, created_at=time.time()
                )
                session.add(record)
            if not saved:
                if record:
                    session.delete(record)
                return None
            return {
                "heritage_id": heritage_id,
                "created_at": timestamp(record.created_at),
                "heritage": catalog_views(session, [heritage])[0],
            }

    def favorites(self, principal, limit, offset):
        with self.db.session() as session:
            require_account(session, principal)
            condition = [
                HeritageFavorite.owner_id == principal.id,
                HeritageSite.content_status == "published",
            ]
            query = (
                select(HeritageFavorite, HeritageSite)
                .join(HeritageSite, HeritageSite.id == HeritageFavorite.heritage_id)
                .where(*condition)
            )
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.execute(
                query.order_by(HeritageFavorite.created_at.desc(), HeritageFavorite.heritage_id)
                .limit(limit)
                .offset(offset)
            ).all()
            views = {
                item["heritage_id"]: item
                for item in catalog_views(session, [heritage for _, heritage in rows])
            }
            return {
                "items": [
                    {
                        "heritage_id": record.heritage_id,
                        "created_at": timestamp(record.created_at),
                        "heritage": views[record.heritage_id],
                    }
                    for record, _ in rows
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }


def conversation_router(*, runtime_dependency, principal_dependency):
    router = APIRouter(prefix="/api/v1", tags=["Conversations"])
    runtime = Annotated[object, Depends(runtime_dependency)]
    owner = Annotated[object, Depends(principal_dependency)]
    page_limit = Annotated[int, Query(ge=1, le=100)]
    page_offset = Annotated[int, Query(ge=0)]

    @router.post("/conversations", response_model=ConversationView, status_code=201)
    def create(body: ConversationCreate, principal: owner, rt: runtime):
        return ConversationStore(rt.db).create(principal.id, body)

    @router.get("/conversations", response_model=ConversationPage)
    def list_conversations(
        principal: owner, rt: runtime, limit: page_limit = 20, offset: page_offset = 0
    ):
        return ConversationStore(rt.db).list(principal.id, limit, offset)

    @router.get("/conversations/{conversation_id}", response_model=ConversationView)
    def get(conversation_id: UUID, principal: owner, rt: runtime):
        return ConversationStore(rt.db).get(principal.id, conversation_id)

    @router.patch("/conversations/{conversation_id}", response_model=ConversationView)
    def patch(conversation_id: UUID, body: ConversationPatch, principal: owner, rt: runtime):
        return ConversationStore(rt.db).patch(principal.id, conversation_id, body)

    @router.delete("/conversations/{conversation_id}", status_code=204)
    def remove(conversation_id: UUID, principal: owner, rt: runtime):
        ConversationStore(rt.db).delete(principal.id, conversation_id)
        return Response(status_code=204)

    @router.get("/conversations/{conversation_id}/messages", response_model=MessagePage)
    def messages(
        conversation_id: UUID,
        principal: owner,
        rt: runtime,
        limit: page_limit = 50,
        offset: page_offset = 0,
    ):
        return ConversationStore(rt.db).messages(principal.id, conversation_id, limit, offset)

    @router.get("/conversations/{conversation_id}/memory")
    def memory(conversation_id: UUID, principal: owner, rt: runtime):
        return ConversationStore(rt.db).memory(principal.id, conversation_id)

    @router.delete("/conversations/{conversation_id}/memory", status_code=204)
    def clear_memory(conversation_id: UUID, principal: owner, rt: runtime):
        ConversationStore(rt.db).clear_memory(principal.id, conversation_id)
        return Response(status_code=204)

    @router.get("/users/me/heritage-favorites", response_model=FavoritePage)
    def favorites(principal: owner, rt: runtime, limit: page_limit = 20, offset: page_offset = 0):
        return ConversationStore(rt.db).favorites(principal, limit, offset)

    @router.put("/users/me/heritage-favorites/{heritage_id}", response_model=FavoriteView)
    def favorite(heritage_id: str, principal: owner, rt: runtime):
        return ConversationStore(rt.db).favorite(principal, heritage_id, True)

    @router.delete("/users/me/heritage-favorites/{heritage_id}", status_code=204)
    def unfavorite(heritage_id: str, principal: owner, rt: runtime):
        ConversationStore(rt.db).favorite(principal, heritage_id, False)
        return Response(status_code=204)

    return router
