"""
Async-friendly wrapper for Firestore operations.
Wraps blocking Firestore calls with asyncio.to_thread() to prevent event loop blocking.
"""

import asyncio
import logging
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Firestore client singleton (thread-safe)
_firestore_client = None
_lock = asyncio.Lock()


def async_firestore_operation(func: Callable) -> Callable:
    """Decorator to run blocking Firestore operations in thread pool."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except Exception as e:
            logger.error(f"Firestore async operation failed in {func.__name__}: {e}")
            raise
    return wrapper


class AsyncFirestoreClient:
    """Async wrapper for Firestore client."""

    def __init__(self, db=None):
        """Initialize with a Firestore client (or None to lazy-load)."""
        self.db = db

    async def _ensure_client(self):
        """Lazy-load Firestore client on first access."""
        if self.db is None:
            from src.config.firebase_config import get_firestore_client
            self.db = get_firestore_client()
            if self.db is None:
                raise RuntimeError("Firestore client not available")
        return self.db

    async def get_document(self, collection: str, document_id: str) -> dict | None:
        """Async get a single document."""
        db = await self._ensure_client()

        def _get():
            doc = db.collection(collection).document(document_id).get()
            return doc.to_dict() if doc.exists else None

        return await asyncio.to_thread(_get)

    async def list_collection(
        self, collection: str, limit: int = 1000
    ) -> list[dict]:
        """Async list documents in a collection."""
        db = await self._ensure_client()

        def _list():
            docs = db.collection(collection).limit(limit).stream()
            return [doc.to_dict() for doc in docs]

        return await asyncio.to_thread(_list)

    async def write_document(
        self, collection: str, document_id: str, data: dict, merge: bool = False
    ) -> None:
        """Async write a document."""
        db = await self._ensure_client()

        def _write():
            db.collection(collection).document(document_id).set(data, merge=merge)

        return await asyncio.to_thread(_write)

    async def update_document(self, collection: str, document_id: str, data: dict) -> None:
        """Async update a document."""
        db = await self._ensure_client()

        def _update():
            db.collection(collection).document(document_id).update(data)

        return await asyncio.to_thread(_update)

    async def delete_document(self, collection: str, document_id: str) -> None:
        """Async delete a document."""
        db = await self._ensure_client()

        def _delete():
            db.collection(collection).document(document_id).delete()

        return await asyncio.to_thread(_delete)

    async def query(
        self, collection: str, field: str, op: str, value: Any, limit: int = 100
    ) -> list[dict]:
        """Async query documents."""
        db = await self._ensure_client()

        def _query():
            query_ref = db.collection(collection).where(field, op, value).limit(limit)
            docs = query_ref.stream()
            return [doc.to_dict() for doc in docs]

        return await asyncio.to_thread(_query)

    async def batch_write(self, operations: list[tuple[str, str, dict]]) -> None:
        """Async batch write operations.

        Args:
            operations: List of (collection, doc_id, data) tuples
        """
        db = await self._ensure_client()

        def _batch():
            batch = db.batch()
            for collection, doc_id, data in operations:
                batch.set(db.collection(collection).document(doc_id), data, merge=True)
            batch.commit()

        return await asyncio.to_thread(_batch)

    async def get_subcollection(
        self, collection: str, document_id: str, subcollection: str
    ) -> list[dict]:
        """Async get a subcollection."""
        db = await self._ensure_client()

        def _get_subcoll():
            docs = (
                db.collection(collection)
                .document(document_id)
                .collection(subcollection)
                .stream()
            )
            return [doc.to_dict() for doc in docs]

        return await asyncio.to_thread(_get_subcoll)


# Global async Firestore client instance
_async_client: AsyncFirestoreClient | None = None


def get_async_firestore_client() -> AsyncFirestoreClient:
    """Get the global async Firestore client."""
    global _async_client
    if _async_client is None:
        from src.config.firebase_config import get_firestore_client
        db = get_firestore_client()
        _async_client = AsyncFirestoreClient(db)
    return _async_client
