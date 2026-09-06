"""MongoDB provider: CRUD and aggregation via motor async driver."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderHealth,
    action,
)


class MongoDBProvider(BaseIntegrationProvider):
    provider_key = "mongodb"
    name = "MongoDB"
    description = "Query and mutate MongoDB collections and run aggregations."
    auth_type = "token"
    base_url = ""
    timeout = 30.0
    supports_webhooks = False

    capabilities = [
        Capability(
            name="list_collections",
            description="List collection names in the database.",
            params_schema={},
        ),
        Capability(
            name="insert_one",
            description="Insert a single document.",
            params_schema={
                "required": ["collection", "document"],
                "properties": {"collection": {"type": "string"}, "document": {"type": "object"}},
            },
        ),
        Capability(
            name="insert_many",
            description="Insert multiple documents.",
            params_schema={
                "required": ["collection", "documents"],
                "properties": {
                    "collection": {"type": "string"},
                    "documents": {"type": "array"},
                },
            },
        ),
        Capability(
            name="find",
            description="Find documents matching a filter.",
            params_schema={
                "required": ["collection"],
                "properties": {
                    "collection": {"type": "string"},
                    "filter": {"type": "object"},
                    "limit": {"type": "integer"},
                    "sort": {"type": "object"},
                },
            },
        ),
        Capability(
            name="find_one",
            description="Find a single document matching a filter.",
            params_schema={
                "required": ["collection"],
                "properties": {"collection": {"type": "string"}, "filter": {"type": "object"}},
            },
        ),
        Capability(
            name="update_one",
            description="Update a single document matching a filter.",
            params_schema={
                "required": ["collection", "filter", "update"],
                "properties": {
                    "collection": {"type": "string"},
                    "filter": {"type": "object"},
                    "update": {"type": "object"},
                    "upsert": {"type": "boolean"},
                },
            },
        ),
        Capability(
            name="delete_one",
            description="Delete a single document matching a filter.",
            params_schema={
                "required": ["collection", "filter"],
                "properties": {"collection": {"type": "string"}, "filter": {"type": "object"}},
            },
        ),
        Capability(
            name="delete_many",
            description="Delete all documents matching a filter.",
            params_schema={
                "required": ["collection", "filter"],
                "properties": {"collection": {"type": "string"}, "filter": {"type": "object"}},
            },
        ),
        Capability(
            name="aggregate",
            description="Run an aggregation pipeline.",
            params_schema={
                "required": ["collection", "pipeline"],
                "properties": {
                    "collection": {"type": "string"},
                    "pipeline": {"type": "array"},
                },
            },
        ),
        Capability(
            name="count_documents",
            description="Count documents matching a filter.",
            params_schema={
                "required": ["collection"],
                "properties": {"collection": {"type": "string"}, "filter": {"type": "object"}},
            },
        ),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._motor: Any = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(self.timeout)
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout,
                limits=limits,
                headers=self.base_headers,
            )
        return self._client

    # ------------------------------------------------------------------ helpers

    def _creds(self) -> dict[str, Any]:
        if self.context is None:
            return {}
        return self.context.credentials

    def _connect(self) -> Any:
        """Lazily build the motor client (import inside method; never at module top)."""
        if self._motor is None:
            import motor.motor_asyncio

            uri = self._creds().get("uri") or ""
            self._motor = motor.motor_asyncio.AsyncIOMotorClient(uri)
        return self._motor

    def _db_name(self) -> str:
        from config import settings

        return self._creds().get("database") or settings.mongodb_db_name or "agentforge"

    def _collection(self, name: str) -> Any:
        return self._connect()[self._db_name()][name]

    @staticmethod
    def _jsonable(doc: Any) -> Any:
        if isinstance(doc, dict):
            return {k: MongoDBProvider._jsonable(v) for k, v in doc.items()}
        if isinstance(doc, list):
            return [MongoDBProvider._jsonable(v) for v in doc]
        if isinstance(doc, datetime):
            return doc.isoformat()
        try:
            import bson

            if isinstance(doc, bson.ObjectId):
                return str(doc)
        except Exception:
            pass
        return doc

    # ------------------------------------------------------------------ lifecycle

    async def validate_connection(self) -> bool:
        result = await self._connect().admin.command("ping")
        return bool(result and result.get("ok"))

    async def health(self) -> ProviderHealth:
        try:
            ok = await self.validate_connection()
            if ok:
                return ProviderHealth.healthy(detail={"database": self._db_name()})
            return ProviderHealth.down(detail={"reason": "ping failed"})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    async def refresh_token(self) -> bool:
        return False

    async def disconnect(self) -> None:
        if self._motor is not None and hasattr(self._motor, "close"):
            self._motor.close()
        self._motor = None
        await self.aclose()

    # ------------------------------------------------------------------ actions

    @action("list_collections")
    async def list_collections(self) -> dict[str, Any]:
        names = await self._connect()[self._db_name()].list_collection_names()
        return {"collections": list(names)}

    @action("insert_one")
    async def insert_one(self, collection: str, document: dict[str, Any]) -> dict[str, Any]:
        res = await self._collection(collection).insert_one(document)
        return {"inserted_id": str(res.inserted_id)}

    @action("insert_many")
    async def insert_many(self, collection: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
        res = await self._collection(collection).insert_many(documents)
        return {"inserted_ids": [str(i) for i in res.inserted_ids]}

    @action("find")
    async def find(
        self,
        collection: str,
        filter: dict[str, Any] | None = None,
        limit: int = 100,
        sort: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cursor = self._collection(collection).find(filter or {})
        if sort:
            sort_list = [(k, v) for k, v in (sort or {}).items()]
            cursor = cursor.sort(sort_list)
        rows = await cursor.limit(limit).to_list(length=limit)
        documents = [self._jsonable(d) for d in rows]
        return {"documents": documents, "count": len(documents)}

    @action("find_one")
    async def find_one(self, collection: str, filter: dict[str, Any] | None = None) -> Any:
        doc = await self._collection(collection).find_one(filter or {})
        return self._jsonable(doc) if doc else None

    @action("update_one")
    async def update_one(
        self,
        collection: str,
        filter: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False,
    ) -> dict[str, Any]:
        res = await self._collection(collection).update_one(filter, {"$set": update}, upsert=upsert)
        return {
            "modified_count": res.modified_count,
            "matched_count": res.matched_count,
            "upserted_id": str(res.upserted_id) if res.upserted_id else None,
        }

    @action("delete_one")
    async def delete_one(self, collection: str, filter: dict[str, Any]) -> dict[str, Any]:
        res = await self._collection(collection).delete_one(filter)
        return {"deleted_count": res.deleted_count}

    @action("delete_many")
    async def delete_many(self, collection: str, filter: dict[str, Any]) -> dict[str, Any]:
        res = await self._collection(collection).delete_many(filter)
        return {"deleted_count": res.deleted_count}

    @action("aggregate")
    async def aggregate(self, collection: str, pipeline: list[dict[str, Any]]) -> dict[str, Any]:
        cursor = self._collection(collection).aggregate(pipeline)
        rows = await cursor.to_list(length=None)
        return {"documents": [self._jsonable(d) for d in rows]}

    @action("count_documents")
    async def count_documents(self, collection: str, filter: dict[str, Any] | None = None) -> dict[str, Any]:
        count = await self._collection(collection).count_documents(filter or {})
        return {"count": int(count)}


ProviderCls = MongoDBProvider
provider = MongoDBProvider()
