"""OneNote and Microsoft Graph Authentication Client using MSAL and SQLite Cache."""

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import msal
import requests

from onebridge.auth.sqlite_cache import SQLiteTokenCache
from onebridge.config import AUTHORITY, CLIENT_ID, DB_PATH, DEFAULT_PLACEHOLDER_CLIENT_ID, GRAPH_API_BASE, SCOPES
from onebridge.logger import get_logger

logger = get_logger("onebridge.auth.client")

# Reserved OIDC scopes that MSAL includes by default and disallows in scope lists
RESERVED_SCOPES = {"openid", "profile", "offline_access"}


class OneNoteAuthenticator:
    """Manages Microsoft authentication lifecycle, token refresh, and persistence."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        authority: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        db_path: Path = DB_PATH,
    ):
        self.cache = SQLiteTokenCache(db_path=db_path)
        cached_meta = self.cache.get_account_metadata() or {}
        stored_client_id = cached_meta.get("client_id") or self.cache.get_stored_client_id()
        stored_authority = cached_meta.get("authority")

        # Resolve client_id: explicit param -> env var -> cached DB client_id -> config default
        if client_id:
            self.client_id = client_id
        elif "ONEBRIDGE_CLIENT_ID" in os.environ or "ONENOTE_CLIENT_ID" in os.environ:
            self.client_id = CLIENT_ID
        elif stored_client_id:
            self.client_id = stored_client_id
        else:
            self.client_id = CLIENT_ID

        # Resolve authority: explicit param -> env var -> cached DB authority -> config default
        if authority:
            self.authority = authority
        elif "ONEBRIDGE_AUTHORITY" in os.environ or "ONENOTE_AUTHORITY" in os.environ:
            self.authority = AUTHORITY
        elif stored_authority:
            self.authority = stored_authority
        else:
            self.authority = AUTHORITY

        # Filter out any reserved scopes to prevent MSAL ValueError
        raw_scopes = scopes or SCOPES
        self.scopes = [s for s in raw_scopes if s.lower() not in RESERVED_SCOPES]

        self.app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            token_cache=self.cache,
        )

        # If we recovered a client_id from tokens but it wasn't saved in metadata, backfill it
        if stored_client_id and not cached_meta.get("client_id"):
            self.cache.save_if_changed(
                username=cached_meta.get("username"),
                account_id=cached_meta.get("account_id"),
                tenant_id=cached_meta.get("tenant_id"),
                client_id=self.client_id,
                authority=self.authority,
                force=True,
            )

    def _persist_account_state(self, auth_result: Dict[str, Any], force: bool = False) -> None:
        """Helper to extract account details from auth result and persist token cache."""
        username = None
        account_id = None
        tenant_id = None

        if "id_token_claims" in auth_result:
            claims = auth_result["id_token_claims"]
            username = (
                claims.get("preferred_username")
                or claims.get("email")
                or claims.get("upn")
            )
            account_id = claims.get("oid") or claims.get("sub")
            tenant_id = claims.get("tid")

        self.cache.save_if_changed(
            username=username,
            account_id=account_id,
            tenant_id=tenant_id,
            client_id=self.client_id,
            authority=self.authority,
            force=force,
        )

    def get_token_silently(self) -> Optional[Dict[str, Any]]:
        """Attempt to acquire a valid access token silently from cache or via refresh token.
        
        Returns:
            Dict containing 'access_token' if successful, or None if user interaction is required.
        """
        accounts = self.app.get_accounts()
        if not accounts:
            logger.debug("Nenhuma conta encontrada no cache para renovação silenciosa.")
            return None

        # Attempt silent acquisition using the primary cached account
        result = self.app.acquire_token_silent(
            scopes=self.scopes,
            account=accounts[0],
        )

        if result and "access_token" in result:
            logger.debug(f"Token renovado silenciosamente com sucesso para {accounts[0].get('username')}.")
            self._persist_account_state(result)
            return result

        logger.warning("Falha na renovação silenciosa de token. Reautenticação necessária.")
        return None

    def get_valid_token(self) -> str:
        """Obtain a valid access token. Raises RuntimeError if not authenticated."""
        token_data = self.get_token_silently()
        if not token_data or "access_token" not in token_data:
            logger.warning("Tentativa de obter token válido sem sessão ativa ou com token expirado.")
            raise RuntimeError(
                "Nenhuma sessão ativa ou o token expirou. Execute 'onebridge login' para autenticar."
            )
        return token_data["access_token"]

    def login_device_flow(
        self, prompt_callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """Initiate OAuth 2.0 Device Code Flow.
        
        Ideal for terminal / CLI usage. Displays a code and URL for the user to authorize
        in any browser.
        """
        logger.info("Iniciando fluxo de autenticação Device Code Flow.")
        flow = self.app.initiate_device_flow(scopes=self.scopes)
        if "user_code" not in flow:
            error_desc = flow.get("error_description", "Falha ao iniciar o fluxo de dispositivo.")
            logger.error(f"Erro no Device Code Flow: {error_desc}")
            raise RuntimeError(f"Erro no Device Code Flow: {error_desc}")

        if prompt_callback:
            prompt_callback(flow["message"])
        else:
            print(flow["message"])

        result = self.app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            logger.info("Autenticação via Device Code Flow concluída com sucesso.")
            self._persist_account_state(result, force=True)
            return result
        else:
            error_msg = result.get("error_description") or result.get("error", "Falha na autenticação.")
            logger.error(f"Falha na autenticação via Device Code Flow: {error_msg}")
            raise RuntimeError(f"Falha no login: {error_msg}")

    def login_interactive(self, port: Optional[int] = None) -> Dict[str, Any]:
        """Initiate interactive browser login on localhost.
        
        Opens the system default browser and listens on a local loopback port for the OAuth callback.
        """
        logger.info("Iniciando fluxo de autenticação interativa via navegador.")
        result = self.app.acquire_token_interactive(
            scopes=self.scopes,
            port=port,
        )
        if "access_token" in result:
            logger.info("Autenticação interativa via navegador concluída com sucesso.")
            self._persist_account_state(result, force=True)
            return result
        else:
            error_msg = result.get("error_description") or result.get("error", "Falha na autenticação interativa.")
            logger.error(f"Falha na autenticação interativa: {error_msg}")
            raise RuntimeError(f"Falha no login: {error_msg}")

    def get_current_user_profile(self) -> Dict[str, Any]:
        """Fetch user profile information from Microsoft Graph /v1.0/me."""
        logger.debug("Consultando perfil do usuário atual no Microsoft Graph (/me)...")
        token = self.get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        response = requests.get(f"{GRAPH_API_BASE}/me", headers=headers, timeout=10)
        if response.status_code == 200:
            profile = response.json()
            logger.debug(f"Perfil recuperado com sucesso: {profile.get('displayName')} ({profile.get('userPrincipalName')})")
            return profile
        elif response.status_code == 401:
            logger.error("Token inválido ou expirado ao consultar perfil no Microsoft Graph.")
            raise RuntimeError("Token inválido ou expirado. Execute 'onebridge login'.")
        else:
            logger.error(f"Falha ao consultar perfil no Microsoft Graph ({response.status_code}): {response.text}")
            raise RuntimeError(
                f"Falha ao consultar perfil no Microsoft Graph ({response.status_code}): {response.text}"
            )

    def logout(self) -> None:
        """Clear all active accounts and delete persistent cache records."""
        logger.info("Encerrando sessão ativa e limpando cache de tokens...")
        accounts = self.app.get_accounts()
        for account in accounts:
            self.app.remove_account(account)
        self.cache.clear()
        logger.info("Sessão encerrada com sucesso.")

    def get_cached_metadata(self) -> Optional[Dict[str, Any]]:
        """Retrieve stored account metadata from SQLite."""
        return self.cache.get_account_metadata()
