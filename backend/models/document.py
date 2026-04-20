import json
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime,
    ForeignKey, Text, Enum, Float
)
from sqlalchemy.orm import relationship

from backend.models.database import Base


class DocumentStatus(str, PyEnum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    READY = "READY"
    FAILED = "FAILED"


class ContentType(str, PyEnum):
    TEXT = "TEXT"
    TABLE = "TABLE"
    FIGURE = "FIGURE"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False, unique=True)
    file_hash = Column(String(64), nullable=False, unique=True)
    size_bytes = Column(BigInteger, nullable=False)
    page_count = Column(Integer, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    index_path = Column(String(512), nullable=True)
    status = Column(
        Enum(DocumentStatus),
        nullable=False,
        default=DocumentStatus.PENDING,
    )
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "size_bytes": self.size_bytes,
            "page_count": self.page_count,
            "chunk_count": self.chunk_count,
            "status": self.status.value if self.status else None,
            "error_message": self.error_message,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    content_type = Column(
        Enum(ContentType),
        nullable=False,
        default=ContentType.TEXT,
    )
    page_number = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=True)
    section_title = Column(String(255), nullable=True)
    version = Column(String(64), nullable=True)
    token_count = Column(Integer, nullable=False, default=0)
    faiss_index_id = Column(Integer, nullable=True)
    annotation_types = Column(Text, nullable=True)
    memo_content = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    document = relationship("Document", back_populates="chunks")

    def to_metadata(self) -> dict:
        return {
            "source": self.document.file_path if self.document else None,
            "page": self.page_number,
            "doc_id": self.document_id,
            "section": self.section_title,
            "version": self.version,
            "chunk_id": self.id,
            "content_type": self.content_type.value if self.content_type else None,
            "annotations": json.loads(self.annotation_types) if self.annotation_types else {},
            "annotation_types": list(json.loads(self.annotation_types).keys()) if self.annotation_types else [],
            "memo_content": self.memo_content,
        }
