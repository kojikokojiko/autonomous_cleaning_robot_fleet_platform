import uuid
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class FirmwareORM(Base):
    __tablename__ = "firmware"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version          = Column(String(32), unique=True, nullable=False)
    s3_key           = Column(String(512), nullable=False)
    checksum_sha256  = Column(String(64), nullable=False)
    file_size_bytes  = Column(BigInteger)
    release_notes    = Column(Text)
    is_stable        = Column(Boolean, default=False)
    uploaded_by      = Column(String(128))
    uploaded_at      = Column(DateTime(timezone=True), server_default=text("NOW()"))


class OTAJobORM(Base):
    __tablename__ = "ota_jobs"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firmware_id   = Column(UUID(as_uuid=True), nullable=False)
    robot_id      = Column(UUID(as_uuid=True), nullable=False)
    strategy      = Column(String(32), default="rolling")
    status        = Column(String(32), default="pending")
    attempts      = Column(Integer, default=0)
    error_message = Column(Text)
    created_at    = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at    = Column(DateTime(timezone=True), server_default=text("NOW()"))
