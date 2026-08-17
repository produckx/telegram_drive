from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

from config.database import Base


class File(Base):
    __tablename__ = "files"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    owner_user_id = Column(Integer, nullable=False, index=True, default=0, comment="Folder creator / owner")
    uploaded_by_user_id = Column(Integer, nullable=False, index=True, default=0, comment="Who uploaded the file")
    folder_id = Column(BigInteger, ForeignKey("folders.id"), nullable=True, index=True)
    message_id = Column(BigInteger, unique=True, nullable=False, index=True)
    name = Column(String(512), nullable=False)
    size = Column(BigInteger, nullable=False, default=0)
    mime_type = Column(String(255), nullable=True)
    file_ext = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    encryption_state = Column(String(50), default="plain")
    is_favorite = Column(Integer, default=0)
    is_pinned = Column(Integer, default=0)

    # Relationships
    folder = relationship("Folder", back_populates="files")


class Folder(Base):
    __tablename__ = "folders"

    id = Column(BigInteger, primary_key=True, index=True)
    owner_user_id = Column(Integer, nullable=False, index=True, default=0)
    parent_id = Column(BigInteger, ForeignKey("folders.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    username = Column(String(255), nullable=True)
    is_public = Column(Integer, default=0)
    group_id = Column(Integer, nullable=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    files = relationship("File", back_populates="folder")
    parent = relationship("Folder", remote_side=[id], backref="children")


class EncryptedFile(Base):
    __tablename__ = "encrypted_files"

    folder_key = Column(String(255), primary_key=True)
    message_id = Column(BigInteger, primary_key=True)
    file_uuid = Column(String(255), nullable=False)
    envelope_version = Column(Integer, nullable=False)
    cipher_suite = Column(Integer, nullable=False)
    ciphertext_size = Column(BigInteger, nullable=False)
    plaintext_size = Column(BigInteger, nullable=True)
    remote_name = Column(String(512), nullable=False)
    key_profile_id = Column(String(255), nullable=True)
    protection_mode = Column(String(50), default="vault")
    metadata_protected = Column(Integer, default=0)
    header_blob = Column(Text, nullable=True)
    header_sha256 = Column(String(64), nullable=True)
    record_state = Column(String(50), default="active")
    reconciliation_state = Column(String(50), default="ok")
    created_at = Column(BigInteger, nullable=False)
    last_verified_at = Column(BigInteger, nullable=True)


class SharedLink(Base):
    __tablename__ = "shared_links"

    id = Column(String(32), primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    folder_id = Column(BigInteger, nullable=True)
    message_id = Column(BigInteger, nullable=False)
    file_name = Column(String(512), nullable=False)
    file_size = Column(BigInteger, nullable=False, default=0)
    password_hash = Column(String(255), nullable=True)
    expires_at = Column(BigInteger, nullable=True)
    revoked = Column(Integer, default=0)
    created_at = Column(BigInteger, nullable=False)


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    color_hex = Column(String(7), default="#3B82F6")
    display_order = Column(Integer, default=0)


Index("ix_encrypted_files_folder_key", EncryptedFile.folder_key)
Index("ix_encrypted_files_record_state", EncryptedFile.record_state)
Index("ix_shared_links_folder_id", SharedLink.folder_id)
Index("ix_shared_links_message_id", SharedLink.message_id)