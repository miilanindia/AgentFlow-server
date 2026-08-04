import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import ForeignKey, String, Text, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.database.base import Base

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

class BrowserSession(TimestampMixin, Base):
    __tablename__ = "browser_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)
    
    # Relationships
    task: Mapped[Optional["Task"]] = relationship(back_populates="browser_sessions")
    timeline_events: Mapped[List["TimelineEvent"]] = relationship(back_populates="browser_session", cascade="all, delete-orphan")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    
    # Relationships
    browser_sessions: Mapped[List["BrowserSession"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    timeline_events: Mapped[List["TimelineEvent"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    job_result: Mapped[Optional["JobResult"]] = relationship(back_populates="task", uselist=False, cascade="all, delete-orphan")


class TimelineEvent(TimestampMixin, Base):
    __tablename__ = "timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    browser_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("browser_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Relationships
    task: Mapped["Task"] = relationship(back_populates="timeline_events")
    browser_session: Mapped[Optional["BrowserSession"]] = relationship(back_populates="timeline_events")

    __table_args__ = (
        Index("ix_timeline_events_task_id_event_type", "task_id", "event_type"),
    )


class JobResult(TimestampMixin, Base):
    __tablename__ = "job_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    task: Mapped["Task"] = relationship(back_populates="job_result")

# Make sure all models are imported before alembic metadata reads them.
metadata = Base.metadata

