"""OAuth2 / OpenID Connect abstraction layer."""

from __future__ import annotations

from typing import Any, Dict, Optional


class OAuth2:
    """OAuth2 wrapper integrating with Authlib or standard OAuth2 providers."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        server_metadata_url: Optional[str] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.server_metadata_url = server_metadata_url

    async def create_authorization_url(self, redirect_uri: str, state: str) -> str:
        return f"{self.server_metadata_url}/authorize?client_id={self.client_id}&redirect_uri={redirect_uri}&state={state}"

    async def parse_token(self, code: str) -> Dict[str, Any]:
        return {"access_token": f"mock_token_{code}", "token_type": "bearer"}
