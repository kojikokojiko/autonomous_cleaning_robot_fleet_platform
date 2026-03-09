import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class MissionORM(Base):
    __tablename__ = "missions"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name           = Column(String(128), nullable=False)
    facility       = Column(String(128))
    zone           = Column(String(64), nullable=False)
    priority       = Column(Integer, nullable=False, default=5)
    status         = Column(String(32), nullable=False, default="pending")
    assigned_robot = Column(UUID(as_uuid=True))
    scheduled_at   = Column(DateTime(timezone=True), nullable=False)
    started_at     = Column(DateTime(timezone=True))
    completed_at   = Column(DateTime(timezone=True))
    coverage_pct   = Column(Float, default=0.0)
    created_by     = Column(String(128))
    created_at     = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at     = Column(DateTime(timezone=True), server_default=text("NOW()"))
