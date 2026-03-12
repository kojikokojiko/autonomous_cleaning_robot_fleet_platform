import uuid

from sqlalchemy import Column, DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class TwinSnapshotORM(Base):
    __tablename__ = "twin_snapshots"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    robot_id       = Column(String(64), nullable=False)
    state          = Column(JSONB, nullable=False)
    snapshotted_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
