
import httpx


class APIKeyAuth(httpx.Auth):
    """Helper to attach API key to requests, compatible with both callable and httpx.Auth."""

    def __init__(
        self,
        api_key: str,
        header_name: str = "Authorization",
        prefix: str = "token",
    ) -> None:
        self.api_key = api_key
        self.header_name = header_name
        self.prefix = prefix

    def apply(self, headers: dict[str, str]) -> dict[str, str]:
        if self.prefix:
            headers[self.header_name] = f"{self.prefix} {self.api_key}"
        else:
            headers[self.header_name] = self.api_key
        return headers

    # Support for direct call (used in tests)
    async def __call__(self, request: httpx.Request) -> httpx.Request:
        headers = dict(request.headers)
        self.apply(headers)
        request.headers.update(headers)
        return request

    # httpx.Auth interface
    async def async_auth_flow(self, request: httpx.Request):
        headers = dict(request.headers)
        self.apply(headers)
        request.headers.update(headers)
        yield request