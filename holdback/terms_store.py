"""
Tiny JSON store for confirmed contract terms, keyed by Xero ContactID.

Survives a restart (one file at repo root, gitignored). Holds only the CONFIRMED values
the user saved on the confirm screen (not the extraction confidence). /new-bill reads
these as defaults for the selected job; every field stays overridable at bill time.
"""

import json

from .storage import data_dir

STORE = data_dir() / "terms_store.json"  # repo root locally, /tmp on Vercel


def load_all() -> dict:
    if STORE.exists():
        try:
            return json.loads(STORE.read_text())
        except Exception:
            return {}
    return {}


def get_terms(contact_id: str) -> dict | None:
    return load_all().get(contact_id)


def save_terms(contact_id: str, terms: dict) -> None:
    data = load_all()
    data[contact_id] = terms
    STORE.write_text(json.dumps(data, indent=2))
