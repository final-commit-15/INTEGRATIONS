"""AWS S3 provider: upload, download, delete, and list objects in an S3 bucket."""

from __future__ import annotations

from typing import Any

from exceptions import IntegrationError
from providers.base import (
    BaseIntegrationProvider,
    Capability,
    ProviderHealth,
    action,
)


class AWS_S3Provider(BaseIntegrationProvider):
    provider_key = "aws_s3"
    name = "AWS S3"
    description = "Upload, download, delete, and list objects in an S3 bucket."
    auth_type = "api_key"
    base_url = ""
    timeout = 30.0
    supports_webhooks = False

    capabilities = [
        Capability(
            name="upload_file",
            description="Upload a string of content to an S3 object.",
            params_schema={
                "required": ["key", "content"],
                "properties": {
                    "key": {"type": "string"},
                    "content": {"type": "string"},
                    "bucket": {"type": "string"},
                    "content_type": {"type": "string"},
                },
            },
        ),
        Capability(
            name="download_file",
            description="Download an S3 object's contents.",
            params_schema={
                "required": ["key"],
                "properties": {"key": {"type": "string"}, "bucket": {"type": "string"}},
            },
        ),
        Capability(
            name="delete_file",
            description="Delete an S3 object.",
            params_schema={
                "required": ["key"],
                "properties": {"key": {"type": "string"}, "bucket": {"type": "string"}},
            },
        ),
        Capability(
            name="list_files",
            description="List objects in an S3 bucket.",
            params_schema={
                "properties": {
                    "prefix": {"type": "string"},
                    "bucket": {"type": "string"},
                    "max_keys": {"type": "integer", "default": 1000},
                },
            },
        ),
        Capability(
            name="presigned_upload_url",
            description="Generate a presigned PUT URL for an object.",
            params_schema={
                "required": ["key"],
                "properties": {"key": {"type": "string"}, "expires_in": {"type": "integer"}, "bucket": {"type": "string"}},
            },
        ),
        Capability(
            name="presigned_download_url",
            description="Generate a presigned GET URL for an object.",
            params_schema={
                "required": ["key"],
                "properties": {"key": {"type": "string"}, "expires_in": {"type": "integer"}},
            },
        ),
        Capability(
            name="file_exists",
            description="Check whether an object exists and its size.",
            params_schema={
                "required": ["key"],
                "properties": {"key": {"type": "string"}, "bucket": {"type": "string"}},
            },
        ),
        Capability(
            name="create_folder",
            description="Create a folder placeholder (zero-byte object ending in a slash).",
            params_schema={
                "required": ["prefix"],
                "properties": {"prefix": {"type": "string"}, "bucket": {"type": "string"}},
            },
        ),
    ]

    async def refresh_token(self) -> bool:
        return False

    @property
    def auth_headers(self) -> dict[str, str]:
        return {}

    @property
    def client(self) -> Any:
        return None

    def _creds(self) -> dict[str, str]:
        if self.context:
            creds = self.context.credentials
            if creds.get("access_key_id") and creds.get("secret_key"):
                return {
                    "access_key_id": creds.get("access_key_id"),
                    "secret_key": creds.get("secret_key"),
                    "region": creds.get("region") or "us-east-1",
                }
        from config import settings

        return {
            "access_key_id": settings.aws_access_key_id,
            "secret_key": settings.aws_secret_access_key.get_secret_value() if settings.aws_secret_access_key else "",
            "region": settings.aws_region,
        }

    def _resolve_bucket(self, bucket: str | None = None) -> str:
        if bucket:
            return bucket
        if self.context and self.context.credentials.get("bucket"):
            return self.context.credentials["bucket"]
        from config import settings

        return settings.aws_s3_bucket

    def _session(self) -> Any:
        try:
            import aioboto3
        except ImportError as exc:
            raise IntegrationError(
                "s3 sdk unavailable",
                provider=self.provider_key,
                details={"reason": "aioboto3 is not installed"},
            ) from exc
        creds = self._creds()
        return aioboto3.Session(
            aws_access_key_id=creds["access_key_id"],
            aws_secret_access_key=creds["secret_key"],
            region_name=creds["region"],
        )

    async def validate_connection(self) -> bool:
        try:
            session = self._session()
            async with session.client("s3") as client:
                await client.head_bucket(Bucket=self._resolve_bucket())
            return True
        except Exception:
            return False

    async def health(self) -> ProviderHealth:
        try:
            valid = await self.validate_connection()
            if valid:
                return ProviderHealth.healthy()
            return ProviderHealth.down(detail={"reason": "head_bucket failed"})
        except Exception as exc:
            return ProviderHealth.down(detail={"error": str(exc)})

    async def _client(self) -> Any:
        session = self._session()
        return session.client("s3")

    @action("upload_file")
    async def upload_file(
        self,
        key: str,
        content: str,
        bucket: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        bucket_name = self._resolve_bucket(bucket)
        async with await self._client() as client:
            kwargs: dict[str, Any] = {"Bucket": bucket_name, "Key": key, "Body": content.encode()}
            if content_type:
                kwargs["ContentType"] = content_type
            await client.put_object(**kwargs)
        return {"key": key, "bucket": bucket_name, "size": len(content)}

    @action("download_file")
    async def download_file(self, key: str, bucket: str | None = None) -> dict[str, Any]:
        bucket_name = self._resolve_bucket(bucket)
        async with await self._client() as client:
            resp = await client.get_object(Bucket=bucket_name, Key=key)
            body = await resp["Body"].read()
            content_type = resp.get("ContentType", "")
        return {"key": key, "body": body.decode("utf-8", errors="replace"), "content_type": content_type}

    @action("delete_file")
    async def delete_file(self, key: str, bucket: str | None = None) -> dict[str, Any]:
        bucket_name = self._resolve_bucket(bucket)
        async with await self._client() as client:
            await client.delete_object(Bucket=bucket_name, Key=key)
        return {"deleted": True, "key": key}

    @action("list_files")
    async def list_files(
        self,
        prefix: str | None = None,
        bucket: str | None = None,
        max_keys: int = 1000,
    ) -> dict[str, Any]:
        bucket_name = self._resolve_bucket(bucket)
        kwargs: dict[str, Any] = {"Bucket": bucket_name, "MaxKeys": max_keys}
        if prefix:
            kwargs["Prefix"] = prefix
        async with await self._client() as client:
            resp = await client.list_objects_v2(**kwargs)
        contents = resp.get("Contents", []) or []
        files = [
            {
                "key": obj.get("Key"),
                "size": obj.get("Size"),
                "last_modified": str(obj.get("LastModified")) if obj.get("LastModified") else None,
            }
            for obj in contents
        ]
        return {"files": files}

    @action("presigned_upload_url")
    async def presigned_upload_url(
        self,
        key: str,
        expires_in: int = 3600,
        bucket: str | None = None,
    ) -> dict[str, Any]:
        bucket_name = self._resolve_bucket(bucket)
        async with await self._client() as client:
            url = await client.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
        return {"url": url, "method": "PUT"}

    @action("presigned_download_url")
    async def presigned_download_url(self, key: str, expires_in: int = 3600) -> dict[str, Any]:
        bucket_name = self._resolve_bucket()
        async with await self._client() as client:
            url = await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
        return {"url": url, "method": "GET"}

    @action("file_exists")
    async def file_exists(self, key: str, bucket: str | None = None) -> dict[str, Any]:
        bucket_name = self._resolve_bucket(bucket)
        try:
            async with await self._client() as client:
                resp = await client.head_object(Bucket=bucket_name, Key=key)
            return {"exists": True, "size": resp.get("ContentLength")}
        except Exception:
            return {"exists": False, "size": None}

    @action("create_folder")
    async def create_folder(self, prefix: str, bucket: str | None = None) -> dict[str, Any]:
        key = prefix.rstrip("/") + "/"
        bucket_name = self._resolve_bucket(bucket)
        async with await self._client() as client:
            await client.put_object(Bucket=bucket_name, Key=key, Body=b"")
        return {"created": True}


ProviderCls = AWS_S3Provider
provider = AWS_S3Provider()
