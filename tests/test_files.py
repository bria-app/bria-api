"""Tests for Files module."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.modules.files.application.use_cases.file import (
    DeleteFile,
    DownloadFile,
    GetFile,
    ListFiles,
    UploadFile,
)
from app.modules.files.domain.entities import StoredFile
from app.modules.files.domain.enums import FileCategory
from app.modules.files.domain.exceptions import StoredFileNotFoundError


class FakeStoredFileRepository:
    def __init__(self) -> None:
        self._store: dict[UUID, StoredFile] = {}

    def get_by_id(self, file_id: UUID) -> StoredFile | None:
        return self._store.get(file_id)

    def list_by_company(
        self,
        company_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[StoredFile]:
        rows = [f for f in self._store.values() if f.company_id == company_id]
        return rows[offset : offset + limit]

    def add(self, stored_file: StoredFile) -> StoredFile:
        if stored_file.id is None:
            stored_file.id = uuid4()
        self._store[stored_file.id] = stored_file
        return stored_file

    def delete(self, file_id: UUID) -> bool:
        return self._store.pop(file_id, None) is not None


class FakeStoragePort:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def save(self, file_name: str, content: bytes, content_type: str) -> str:
        # Just use a fake path
        path = f"fake_storage/{uuid4()}_{file_name}"
        self._store[path] = content
        return path

    def get(self, file_path: str) -> bytes:
        return self._store[file_path]

    def delete(self, file_path: str) -> bool:
        return self._store.pop(file_path, None) is not None


class TestFileUseCases:
    def test_upload_and_list_files(self) -> None:
        repo = FakeStoredFileRepository()
        storage = FakeStoragePort()
        company_id = uuid4()

        uploaded = UploadFile(repo, storage).execute(
            company_id=company_id,
            file_name="test.txt",
            content=b"hello",
            content_type="text/plain",
            category=FileCategory.OTHER,
        )
        assert uploaded.file_name == "test.txt"
        assert uploaded.size_bytes == 5

        files = ListFiles(repo).execute(company_id=company_id)
        assert len(files) == 1
        assert files[0].id == uploaded.id

    def test_get_and_download(self) -> None:
        repo = FakeStoredFileRepository()
        storage = FakeStoragePort()
        company_id = uuid4()

        uploaded = UploadFile(repo, storage).execute(
            company_id=company_id,
            file_name="test.txt",
            content=b"hello",
            content_type="text/plain",
            category=FileCategory.OTHER,
        )

        got = GetFile(repo).execute(company_id=company_id, file_id=uploaded.id)
        assert got.file_name == "test.txt"

        content, name, mime = DownloadFile(repo, storage).execute(
            company_id=company_id, file_id=uploaded.id
        )
        assert content == b"hello"
        assert name == "test.txt"
        assert mime == "text/plain"

    def test_delete_file(self) -> None:
        repo = FakeStoredFileRepository()
        storage = FakeStoragePort()
        company_id = uuid4()

        uploaded = UploadFile(repo, storage).execute(
            company_id=company_id,
            file_name="test.txt",
            content=b"hello",
            content_type="text/plain",
            category=FileCategory.OTHER,
        )

        DeleteFile(repo, storage).execute(company_id=company_id, file_id=uploaded.id)

        with pytest.raises(StoredFileNotFoundError):
            GetFile(repo).execute(company_id=company_id, file_id=uploaded.id)
