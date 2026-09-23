"""Local filesystem storage abstraction for email attachments.

Handles safe filename normalization, directory isolation, UUID-based internal
file storage to prevent path traversal and execution risks, and streaming I/O.
"""

import asyncio
import os
from pathlib import Path
import re
from typing import Optional, Tuple
import uuid
from fastapi import UploadFile

from app.core.config import settings


class AttachmentStorageService:
    """Service providing safe filesystem persistence for email attachments."""

    DISALLOWED_EXTENSIONS = {
        ".exe", ".bat", ".cmd", ".sh", ".ps1", ".psm1", ".vbs", ".vbe",
        ".js", ".jse", ".wsf", ".wsh", ".msc", ".scr", ".msi", ".msp",
        ".com", ".pif", ".cpl", ".jar", ".dll", ".sys",
    }

    @classmethod
    def get_base_upload_dir(cls) -> Path:
        """Resolve and ensure the base upload directory exists."""
        raw_path = Path(settings.UPLOAD_DIR)
        if raw_path.is_absolute():
            base_dir = raw_path.resolve()
        else:
            # Anchor relative upload directory deterministically to the backend directory
            backend_dir = Path(__file__).resolve().parent.parent.parent
            base_dir = (backend_dir / raw_path).resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    @classmethod
    def get_company_account_dir(cls, company_id: int, account_id: int) -> Path:
        """Resolve partitioned directory for a given company and email account."""
        target_dir = cls.get_base_upload_dir() / "attachments" / f"company_{company_id}" / f"account_{account_id}"
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    @classmethod
    def sanitize_filename(cls, original_filename: Optional[str]) -> str:
        """Extract a safe client filename, removing path traversal components."""
        if not original_filename:
            return "attachment.bin"

        # Strip directory traversal characters and paths
        base_name = Path(original_filename).name
        # Remove control characters and null bytes
        clean_name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", base_name).strip()
        # Fallback if entirely stripped
        if not clean_name or clean_name in {".", ".."}:
            clean_name = "attachment.bin"
        return clean_name

    @classmethod
    def validate_filename(cls, filename: str) -> Tuple[bool, Optional[str]]:
        """Validate filename against dangerous executable extensions."""
        ext = Path(filename).suffix.lower()
        if ext in cls.DISALLOWED_EXTENSIONS:
            return False, f"File extension '{ext}' is not allowed for security reasons."
        return True, None

    @classmethod
    async def save_upload_file(
        cls,
        company_id: int,
        account_id: int,
        upload_file: UploadFile,
    ) -> Tuple[str, str, int, str]:
        """Read and store an UploadFile into partitioned storage.
        
        Returns:
            Tuple of (sanitized_original_filename, content_type, file_size_bytes, relative_storage_path)
        """
        raw_filename = upload_file.filename or "attachment.bin"
        safe_original_name = cls.sanitize_filename(raw_filename)

        # Validate extension
        is_valid, err = cls.validate_filename(safe_original_name)
        if not is_valid:
            raise ValueError(err)

        # Generate unique internal file name: <uuid><ext>
        unique_id = uuid.uuid4().hex
        ext = Path(safe_original_name).suffix
        internal_name = f"{unique_id}{ext}"

        dest_dir = cls.get_company_account_dir(company_id, account_id)
        dest_path = dest_dir / internal_name

        # Calculate relative path from base upload dir for database storage
        base_dir = cls.get_base_upload_dir()
        rel_storage_path = str(dest_path.relative_to(base_dir)).replace("\\", "/")

        # Stream content in chunks to track size and enforce limits
        total_size = 0
        chunk_size = 64 * 1024  # 64KB chunks

        try:
            with open(dest_path, "wb") as out_file:
                while True:
                    chunk = await upload_file.read(chunk_size)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > settings.MAX_ATTACHMENT_SIZE_BYTES:
                        raise ValueError(
                            f"File size exceeds maximum limit of {settings.MAX_ATTACHMENT_SIZE_BYTES} bytes."
                        )
                    out_file.write(chunk)
        except Exception:
            if dest_path.exists():
                try:
                    dest_path.unlink()
                except OSError:
                    pass
            raise

        if total_size == 0:
            if dest_path.exists():
                try:
                    dest_path.unlink()
                except OSError:
                    pass
            raise ValueError("Uploaded file is empty (0 bytes).")

        content_type = upload_file.content_type or "application/octet-stream"
        return safe_original_name, content_type, total_size, rel_storage_path

    @classmethod
    def save_attachment_bytes(
        cls,
        company_id: int,
        account_id: int,
        raw_filename: Optional[str],
        content_type: Optional[str],
        content_bytes: bytes,
    ) -> Tuple[str, str, int, str]:
        """Persist raw byte content for an attachment into partitioned storage.

        Returns:
            Tuple of (sanitized_original_filename, content_type, file_size_bytes, relative_storage_path)
        """
        if not content_bytes:
            raise ValueError("Attachment content is empty (0 bytes).")

        total_size = len(content_bytes)
        if total_size > settings.MAX_ATTACHMENT_SIZE_BYTES:
            raise ValueError(
                f"Attachment size ({total_size} bytes) exceeds maximum limit of {settings.MAX_ATTACHMENT_SIZE_BYTES} bytes."
            )

        safe_original_name = cls.sanitize_filename(raw_filename)

        # Validate extension
        is_valid, err = cls.validate_filename(safe_original_name)
        if not is_valid:
            raise ValueError(err)

        unique_id = uuid.uuid4().hex
        ext = Path(safe_original_name).suffix
        internal_name = f"{unique_id}{ext}"

        dest_dir = cls.get_company_account_dir(company_id, account_id)
        dest_path = dest_dir / internal_name

        base_dir = cls.get_base_upload_dir()
        rel_storage_path = str(dest_path.relative_to(base_dir)).replace("\\", "/")

        dest_path.write_bytes(content_bytes)
        clean_content_type = content_type or "application/octet-stream"
        return safe_original_name, clean_content_type, total_size, rel_storage_path

    @classmethod
    def resolve_storage_path(cls, relative_storage_path: str) -> Path:
        """Resolve a stored relative path safely, ensuring it remains within the upload base dir."""
        base_dir = cls.get_base_upload_dir()
        # Normalize and resolve path
        target_path = (base_dir / relative_storage_path).resolve()

        # Fallback: check project root uploads directory if not found in primary base_dir
        if not target_path.is_file():
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            fallback_path = (project_root / "uploads" / relative_storage_path).resolve()
            if fallback_path.is_file():
                target_path = fallback_path
                base_dir = (project_root / "uploads").resolve()

        # Prevent directory traversal attacks
        try:
            target_path.relative_to(base_dir)
        except ValueError:
            raise PermissionError("Access to the specified storage path is forbidden.")

        return target_path

    @classmethod
    async def read_file_bytes(cls, relative_storage_path: str) -> bytes:
        """Read and return complete file bytes from storage."""
        path = cls.resolve_storage_path(relative_storage_path)
        if not path.is_file():
            raise FileNotFoundError("Attachment file not found on disk.")
        return await asyncio.to_thread(path.read_bytes)

    @classmethod
    async def delete_file(cls, relative_storage_path: str) -> bool:
        """Delete stored file from disk if it exists."""
        try:
            path = cls.resolve_storage_path(relative_storage_path)
            if path.is_file():
                await asyncio.to_thread(path.unlink)
                return True
        except Exception:
            pass
        return False

    @classmethod
    def delete_file_sync(cls, relative_storage_path: str) -> bool:
        """Synchronously delete stored file from disk if it exists."""
        try:
            path = cls.resolve_storage_path(relative_storage_path)
            if path.is_file():
                path.unlink()
                return True
        except Exception:
            pass
        return False


attachment_storage_service = AttachmentStorageService
