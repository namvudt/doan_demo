"""Private node-boundary recovery records, never public model evidence."""

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.models import Base, Payload


class NodeCheckpoint(Base):
    __tablename__ = "api_node_checkpoints"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("api_runs.id", ondelete="CASCADE"), primary_key=True
    )
    node: Mapped[str] = mapped_column(String(40), primary_key=True)
    signature: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(Payload)
    updated_at: Mapped[float] = mapped_column(Float)


class RecoveryRequest(Base):
    __tablename__ = "api_recovery_requests"
    run_id: Mapped[str] = mapped_column(
        ForeignKey("api_runs.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    recovery_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[float] = mapped_column(Float)
