"""
Xero OAuth 2.0 (authorization-code flow) + READ-ONLY API client.

⚠️  NO WRITES LIVE HERE. Per CLAUDE.md rule 1 (HARD GATE), no code path may WRITE to
Xero until the user sends the exact message "NUMBERS CONFIRMED". This module performs
GETs only (Organisation, Contacts, Contact CISSettings). The write path (two ACCPAY
bills) is a separate module built later, after the numbers are confirmed.

Per CLAUDE.md rule 5, we never hardcode or cache the CIS rate:
`get_contact_cis_settings` reads it live from the contact each time it is called.

Tokens are persisted to token_store.json (gitignored). offline_access gives us a
refresh token so the ~30-minute access token can be refreshed silently during the
long build.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse
from pathlib import Path

import requests

# Xero identity + API endpoints (stable, not org-specific).
AUTHORIZE_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
CONNECTIONS_URL = "https://api.xero.com/connections"
API_BASE = "https://api.xero.com/api.xro/2.0"

# token_store.json sits at repo root, next to app.py. It is gitignored.
TOKEN_STORE = Path(__file__).resolve().parent.parent / "token_store.json"


# --- env accessors (read at call time so .env is loaded first) --------------
def _client_id() -> str:
    return os.environ["XERO_CLIENT_ID"]


def _client_secret() -> str:
    secret = os.environ.get("XERO_CLIENT_SECRET", "")
    if not secret:
        raise RuntimeError(
            "XERO_CLIENT_SECRET is empty. Generate it in the app's Configuration tab "
            "at developer.xero.com and paste it into .env."
        )
    return secret


def _redirect_uri() -> str:
    return os.environ["XERO_REDIRECT_URI"]


def _scopes() -> str:
    return os.environ["XERO_SCOPES"]


# --- token storage ----------------------------------------------------------
def _load_tokens() -> dict:
    if TOKEN_STORE.exists():
        return json.loads(TOKEN_STORE.read_text())
    return {}


def _save_tokens(tok: dict) -> None:
    tok = dict(tok)
    # Stamp an absolute expiry (with a 60s safety margin) so we refresh proactively.
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 1800)) - 60
    # Preserve the tenant id across refreshes (the refresh response doesn't include it).
    existing = _load_tokens()
    if existing.get("tenant_id") and not tok.get("tenant_id"):
        tok["tenant_id"] = existing["tenant_id"]
    TOKEN_STORE.write_text(json.dumps(tok, indent=2))


def is_connected() -> bool:
    return bool(_load_tokens().get("access_token"))


def granted_scopes() -> str:
    """The scopes actually granted on the stored token (from Xero's token response).
    A write 401 usually means accounting.invoices is NOT in here yet — re-consent needed."""
    return _load_tokens().get("scope", "")


def requested_scopes() -> str:
    """Scopes this app is configured to REQUEST (from .env). If a scope is requested but
    never appears in granted_scopes(), Xero is refusing it (app-config / consent issue)."""
    return os.environ.get("XERO_SCOPES", "")


# --- OAuth flow -------------------------------------------------------------
def build_authorize_url(state: str) -> str:
    """URL to send the user to for consent. `state` guards against CSRF."""
    params = {
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "scope": _scopes(),
        "state": state,
        # Force Xero to re-show the consent screen. Without this, Xero silently reuses a
        # prior approval and never grants newly-added scopes (e.g. accounting.invoices).
        "prompt": "consent",
    }
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


def _basic_auth_header() -> dict:
    raw = f"{_client_id()}:{_client_secret()}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def exchange_code(code: str) -> dict:
    """Swap the authorization code for tokens, then record the tenant id."""
    resp = requests.post(
        TOKEN_URL,
        headers=_basic_auth_header(),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(),
        },
        timeout=30,
    )
    resp.raise_for_status()
    _save_tokens(resp.json())
    _store_tenant_id()
    return _load_tokens()


def _refresh() -> dict:
    tok = _load_tokens()
    if not tok.get("refresh_token"):
        raise RuntimeError("No refresh token — connect via /login first.")
    resp = requests.post(
        TOKEN_URL,
        headers=_basic_auth_header(),
        data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]},
        timeout=30,
    )
    resp.raise_for_status()
    _save_tokens(resp.json())
    return _load_tokens()


def get_access_token() -> str:
    tok = _load_tokens()
    if not tok:
        raise RuntimeError("Not connected — visit /login.")
    if time.time() >= tok.get("expires_at", 0):
        tok = _refresh()
    return tok["access_token"]


# --- tenant selection -------------------------------------------------------
def _store_tenant_id() -> str:
    """GET /connections lists the tenants this token can access; use the first."""
    resp = requests.get(
        CONNECTIONS_URL,
        headers={"Authorization": f"Bearer {get_access_token()}", "Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    conns = resp.json()
    if not conns:
        raise RuntimeError("This token has no connected Xero organisations.")
    tenant_id = conns[0]["tenantId"]
    tok = _load_tokens()
    tok["tenant_id"] = tenant_id
    _save_tokens(tok)
    return tenant_id


def tenant_id() -> str:
    return _load_tokens().get("tenant_id") or _store_tenant_id()


# --- read-only API calls ----------------------------------------------------
def api_get(path: str) -> dict:
    """Authenticated GET against the Accounting API. READS ONLY (see module note)."""
    url = path if path.startswith("http") else f"{API_BASE}/{path.lstrip('/')}"
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {get_access_token()}",
            "Xero-tenant-id": tenant_id(),
            "Accept": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_organisation() -> dict:
    return api_get("Organisation")


def get_contacts() -> dict:
    return api_get("Contacts")


def get_accounts() -> dict:
    """Chart of accounts — used to find the CIS Labour Expense + materials account codes."""
    return api_get("Accounts")


def get_tax_rates() -> dict:
    """Tax rates — used to find the exact 20% VAT-on-expenses TaxType for bill lines."""
    return api_get("TaxRates")


# --- WRITE (requires the accounting.invoices scope; only called on explicit user action) --
def create_bills(invoices: list[dict]) -> dict:
    """POST one or more ACCPAY bills to the Invoices endpoint.

    This is the ONLY write in the codebase. It runs only when the user submits the
    /new-bill form (post-"NUMBERS CONFIRMED"). On error we surface Xero's raw response
    body so scope/validation problems are obvious during the build.
    """
    resp = requests.post(
        f"{API_BASE}/Invoices",
        headers={
            "Authorization": f"Bearer {get_access_token()}",
            "Xero-tenant-id": tenant_id(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={"Invoices": invoices},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Xero {resp.status_code}: {resp.text}")
    return resp.json()


def get_contact_cis_settings(contact_id: str) -> dict:
    """LIVE read of a contact's CIS settings (never cached). Returns the raw JSON so we
    can echo the exact field names before relying on them (CLAUDE.md API-specifics)."""
    return api_get(f"Contacts/{contact_id}/CISSettings")
