# Deploying HoldBack

## Recommended for the live demo: run locally
The redirect URI is already `http://localhost:5000/callback`, the filesystem persists the
OAuth token, and there are no cold starts. `pip install -r requirements.txt && python app.py`.

## Vercel (public URL) — works, with caveats
`vercel.json` routes all traffic to the Flask app (`app.py`). Deploy with the Vercel CLI
(`vercel`) or by importing the Git repo in the Vercel dashboard.

### 1. Set environment variables (Vercel → Project → Settings → Environment Variables)
`.env` is NOT deployed (gitignored). Set these in Vercel:
- `XERO_CLIENT_ID`
- `XERO_CLIENT_SECRET`
- `XERO_REDIRECT_URI` = `https://<your-app>.vercel.app/callback`  ← the Vercel URL, not localhost
- `XERO_SCOPES` = `openid profile email offline_access accounting.settings.read accounting.contacts.read accounting.invoices`
- `FLASK_SECRET` = a random string
- `EXTRACT_PROVIDER` = `gemini`, `EXTRACT_MODEL` = `gemini-2.5-flash`, `GEMINI_API_KEY` = …

### 2. Add the Vercel redirect URI to the Xero app
developer.xero.com → your app → add `https://<your-app>.vercel.app/callback` as a second
redirect URI (keep localhost too). Must match `XERO_REDIRECT_URI` exactly.

### 3. Known caveats on Vercel serverless
- **Ephemeral filesystem.** The OAuth token + saved terms are written to `/tmp` on Vercel
  (`holdback/storage.py`). `/tmp` persists only within a warm instance and is not shared
  across instances — fine for one user clicking through quickly, NOT durable. For real
  persistence: set `HOLDBACK_DATA_DIR` to a mounted disk, or move token/terms to a KV store
  (Vercel KV / Upstash Redis) — see the token/terms helpers in `holdback/`.
- **Function size.** `pdfplumber` (+Pillow/pdfminer) and `google-genai` are heavy. If the
  build exceeds Vercel's function size limit, drop those two lines from `requirements.txt`
  for the Vercel build — the PDF-extraction path degrades gracefully to manual entry and
  everything else still works.

## Better fit for a stateful app: Render / Railway / Fly.io
A long-running process with a writable/persistent disk avoids the `/tmp` problem entirely
and needs no code changes. Set the same env vars + redirect URI there.
