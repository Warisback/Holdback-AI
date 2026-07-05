"""
Where the local JSON stores (OAuth token, saved terms) live.

Local dev  -> repo root (persistent).
Vercel     -> /tmp, because the serverless filesystem is read-only elsewhere. NOTE: /tmp
              is per-instance and ephemeral — fine for a single-user click-through on a
              warm instance, NOT durable. For real persistence use HOLDBACK_DATA_DIR
              pointing at a mounted disk, or move these to a KV store (see DEPLOY.md).
"""

import os
from pathlib import Path


def data_dir() -> Path:
    explicit = os.environ.get("HOLDBACK_DATA_DIR")
    if explicit:
        return Path(explicit)
    if os.environ.get("VERCEL"):  # Vercel sets this in the runtime
        return Path("/tmp")
    return Path(__file__).resolve().parent.parent
