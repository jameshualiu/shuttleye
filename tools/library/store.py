"""Storage for the match library: a small protocol, an in-memory store for tests
and a Firestore store for real runs. Paths are slash paths ("players/abc/views/all")."""
from __future__ import annotations

import copy
from typing import Protocol


class Store(Protocol):
    def get(self, path: str) -> dict | None: ...
    def set(self, path: str, data: dict) -> None: ...  # replaces the document
    def delete(self, path: str) -> None: ...
    def list(self, collection: str, where: tuple[str, str, object] | None = None) -> list[dict]: ...
    def list_ids(self, collection: str) -> list[str]: ...  # ids of documents under a collection path


def _matches(doc: dict, where: tuple[str, str, object] | None) -> bool:
    if where is None:
        return True
    field, op, value = where
    if op != "==":
        raise ValueError(f"unsupported operator {op!r}")
    return doc.get(field) == value


def _check_no_nested_arrays(x, in_list: bool = False) -> None:
    """Firestore rejects an array directly inside an array."""
    if isinstance(x, (list, tuple)):
        if in_list:
            raise ValueError("Firestore does not allow arrays nested directly in arrays")
        for v in x:
            _check_no_nested_arrays(v, True)
    elif isinstance(x, dict):
        for v in x.values():
            _check_no_nested_arrays(v, False)


class MemoryStore:
    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    def get(self, path):
        d = self._docs.get(path)
        return copy.deepcopy(d) if d is not None else None

    def set(self, path, data):
        _check_no_nested_arrays(data)
        self._docs[path] = copy.deepcopy(data)

    def delete(self, path):
        self._docs.pop(path, None)

    def list(self, collection, where=None):
        prefix = collection + "/"
        return [copy.deepcopy(d) for p, d in sorted(self._docs.items())
                if p.startswith(prefix) and "/" not in p[len(prefix):] and _matches(d, where)]

    def list_ids(self, collection):
        # Like Firestore's list_documents: a parent with only subcollection docs still counts.
        prefix = collection + "/"
        return sorted({p[len(prefix):].split("/")[0] for p in self._docs if p.startswith(prefix)})

    def paths(self) -> list[str]:
        return sorted(self._docs)


class FirestoreStore:
    """firebase-admin with Application Default Credentials (set GOOGLE_APPLICATION_CREDENTIALS
    to a service-account file outside the repo). Imported lazily so tests run without it."""

    def __init__(self) -> None:
        import firebase_admin
        from firebase_admin import firestore

        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        self._db = firestore.client()

    def get(self, path):
        snap = self._db.document(path).get()
        return snap.to_dict() if snap.exists else None

    def set(self, path, data):
        self._db.document(path).set(data)  # no merge: replaces the document

    def delete(self, path):
        self._db.document(path).delete()

    def list(self, collection, where=None):
        q = self._db.collection(collection)
        if where is not None:
            q = q.where(*where)
        return [s.to_dict() for s in q.stream()]

    def list_ids(self, collection):
        return sorted(r.id for r in self._db.collection(collection).list_documents())
