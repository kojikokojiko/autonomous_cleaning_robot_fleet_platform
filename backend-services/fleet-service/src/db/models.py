from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, Float, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class RobotORM(Base):
    __tablename__ = "robots"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    robot_id        = Column(String(64), unique=True, nullable=False)
    name            = Column(String(128), nullable=False)
    facility        = Column(String(128))
    model           = Column(String(64))
    firmware_version = Column(String(32))
    status          = Column(String(32), nullable=False, default="offline")
    battery_level   = Column(Float)
    position_x      = Column(Float)
    position_y      = Column(Float)
    position_floor  = Column(Integer, default=1)
    last_seen       = Column(DateTime(timezone=True))
    registered_at   = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at      = Column(
        DateTime(timezone=True), server_default=text("NOW()"), onupdate=datetime.utcnow
    )
