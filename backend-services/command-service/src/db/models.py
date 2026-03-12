import uuid

from sqlalchemy import Column, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class CommandORM(Base):
    __tablename__ = "commands"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    robot_id        = Column(String(64), nullable=False)
    command_type    = Column(String(64), nullable=False)
    payload         = Column(JSONB)
    status          = Column(String(32), nullable=False, default="pending")
    issued_by       = Column(String(128))
    issued_at       = Column(DateTime(timezone=True), server_default=text("NOW()"))
    acknowledged_at = Column(DateTime(timezone=True))
    retry_count     = Column(Integer, default=0)
