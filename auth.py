"""
Informatica session management for CDGC MCP Server.
Handles login, JWT token generation, and per-API header factories.
"""
VERSION = "20260528"

import os
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class AuthError(Exception):
    pass


class InformaticaSession:
    """
    Manages authentication state for all Informatica APIs.

    URL layout derived from 'pod' in credentials.env:
      Login URL:    https://{pod}.informaticacloud.com
      CDGC API URL: https://cdgc-api.{pod}.informaticacloud.com
      IDMC API URL: returned as serverUrl from the login response
    """

    def __init__(self, credentials_path: Optional[str] = None):
        path = credentials_path or str(Path(__file__).parent / "credentials.env")
        load_dotenv(path, override=True)

        pod = os.environ.get("pod", "").strip()
        self.username = os.environ.get("username", "").strip()
        self.password = os.environ.get("password", "").strip()

        if not pod or not self.username or not self.password:
            raise AuthError(
                "credentials.env must contain: pod, username, password"
            )

        self.login_url = f"https://{pod}.informaticacloud.com"
        self.cdgc_api_url = f"https://cdgc-api.{pod}.informaticacloud.com"

        self._session_id: Optional[str] = None
        self._org_id: Optional[str] = None
        self._base_api_url: Optional[str] = None   # IDMC serverUrl (from login)
        self._jwt_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Login / token lifecycle
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Authenticate and obtain session ID, org ID, and base API URL."""
        resp = requests.post(
            f"{self.login_url}/ma/api/v2/user/login",
            json={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise AuthError(f"Login failed {resp.status_code}: {resp.text}")

        data = resp.json()
        self._session_id = data.get("icSessionId")
        self._org_id = data.get("orgUuid")
        self._base_api_url = data.get("serverUrl")

        if not self._session_id or not self._org_id:
            raise AuthError("Login response missing icSessionId or orgUuid")

    def _generate_jwt(self) -> None:
        """Exchange session cookie for a JWT access token (valid ~30 min)."""
        if not self._session_id:
            self.login()

        resp = requests.post(
            f"{self.login_url}/identity-service/api/v1/jwt/Token"
            "?client_id=idmc_api&nonce=1234",
            headers={
                "cookie": f"USER_SESSION={self._session_id}",
                "IDS-SESSION-ID": self._session_id,
            },
            timeout=30,
        )

        if resp.status_code == 401:
            # IDMC session expired — re-login and retry once
            self._session_id = None
            self._org_id = None
            self._base_api_url = None
            self._jwt_token = None
            self.login()
            resp = requests.post(
                f"{self.login_url}/identity-service/api/v1/jwt/Token"
                "?client_id=idmc_api&nonce=1234",
                headers={
                    "cookie": f"USER_SESSION={self._session_id}",
                    "IDS-SESSION-ID": self._session_id,
                },
                timeout=30,
            )

        if resp.status_code != 200:
            raise AuthError(f"JWT generation failed {resp.status_code}: {resp.text}")

        data = resp.json()
        self._jwt_token = data.get("access_token") or data.get("jwt_token")
        self._token_expiry = datetime.now() + timedelta(minutes=27)  # refresh early

    def get_jwt(self) -> str:
        """Return a valid JWT, refreshing automatically when near expiry."""
        if not self._session_id:
            self.login()
        if not self._jwt_token or not self._token_expiry or datetime.now() >= self._token_expiry:
            self._generate_jwt()
        return self._jwt_token

    @property
    def session_id(self) -> str:
        if not self._session_id:
            self.login()
        return self._session_id

    @property
    def org_id(self) -> str:
        if not self._org_id:
            self.login()
        return self._org_id

    @property
    def base_api_url(self) -> str:
        """IDMC serverUrl — available after first login."""
        if not self._base_api_url:
            self.login()
        return self._base_api_url

    # ------------------------------------------------------------------
    # Header factories (one per API family)
    # ------------------------------------------------------------------

    def cdgc_headers(self) -> dict:
        """Headers for CDGC Public API (/data360/...)."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.get_jwt()}",
            "X-INFA-ORG-ID": self.org_id,
            "IDS-SESSION-ID": self.session_id,
        }

    def cdgc_internal_headers(self, product_id: str = "CDGC") -> dict:
        """Headers for CDGC Internal publish/content APIs (ccgf-*)."""
        return {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Authorization": f"Bearer {self.get_jwt()}",
            "x-infa-product-id": product_id,
            "Cookie": f"USER_SESSION={self.session_id}",
        }

    def classification_headers(self) -> dict:
        """Headers for Classification / MCC metadata discovery APIs."""
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.get_jwt()}",
            "IDS-SESSION-ID": self.session_id,
            "X-INFA-PRODUCT-ID": "MCC",
        }

    def workflow_headers(self) -> dict:
        """Headers for Workflow definition APIs (htm-carbon)."""
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.get_jwt()}",
            "IDS-SESSION-ID": self.session_id,
        }

    def cdmp_headers(self) -> dict:
        """Headers for Data Marketplace APIs (public + internal)."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.get_jwt()}",
            "Accept": "application/json",
        }

    def idmc_headers(self) -> dict:
        """Headers for IDMC user/group/role/connection management APIs."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "INFA-SESSION-ID": self.session_id,
            "IDS-SESSION-ID": self.session_id,
        }


# ---------------------------------------------------------------------------
# Module-level singleton — shared across all tool calls within one server run
# ---------------------------------------------------------------------------
_session: Optional[InformaticaSession] = None


def get_session() -> InformaticaSession:
    global _session
    if _session is None:
        _session = InformaticaSession()
    return _session
