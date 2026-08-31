# Deploying VibeMatch (Task #10)

Backend → Fly.io. Frontend → Vercel. See `DECISIONS_LOG.md`'s Task #10 entry for why this split
and why Fly.io over Railway. This doc is the actual step-by-step; everything below assumes you're
running commands from your own machine, inside the repo.

---

## 0. Before you start

- [ ] Fly.io account created, `flyctl` CLI installed and logged in (`fly auth login`)
- [ ] Vercel account created (signed up via GitHub)
- [ ] Verify `.env` has never been committed to git — run this from the repo root and confirm
      BOTH commands return nothing:
      ```powershell
      git log --all --oneline -- backend/.env
      git ls-files | Select-String "\.env$"
      ```
      If either returns something, **stop and rotate both API keys** (generate new ones from the
      Anthropic and Voyage dashboards, revoke the old ones) before deploying — history still holds
      the old keys even if the file's been deleted since.

---

## 1. Deploy the backend to Fly.io

From `backend/`:

```powershell
cd backend
fly launch
```

`fly launch` reads `Dockerfile` and `fly.toml` (already in this repo) and asks a few first-time
questions — app name (or accept the `vibematch-backend` default), region. **When it asks whether
to deploy now, say no** — set secrets first, so the first real deploy already has working keys.

```powershell
fly secrets set ANTHROPIC_API_KEY=your-real-key VOYAGE_API_KEY=your-real-key
```

(Get the actual values from your local `backend/.env` — never type them anywhere that logs
history in plaintext long-term; a fresh terminal session for this is fine.)

```powershell
fly deploy
```

Once it finishes, `fly status` (or the URL it prints) gives you the live backend URL — something
like `https://vibematch-backend.fly.dev`. Verify it's actually alive:

```powershell
curl https://vibematch-backend.fly.dev/
```

Should return `{"message": "VibeMatch backend is alive"}` (the root health-check route in
`main.py`).

---

## 2. Deploy the frontend to Vercel

In the Vercel dashboard: **Add New → Project → import your GitHub repo**, set the project's root
directory to `frontend`. Before the first deploy, add an environment variable:

- `VITE_API_BASE_URL` = the real Fly.io URL from step 1 (e.g. `https://vibematch-backend.fly.dev`)

Deploy. Vercel gives you a URL like `https://vibematch-xyz.vercel.app`.

(CLI alternative: `npm install -g vercel`, then `vercel` from inside `frontend/` — it'll prompt
for the same env var on first deploy.)

---

## 3. Close the loop: tell the backend about the real frontend URL

The backend's CORS config (`main.py`) only allows requests from `localhost` until you set
`FRONTEND_ORIGIN` explicitly — otherwise the browser will block every request from the deployed
frontend even though the backend itself is up. Back in `backend/`:

```powershell
fly secrets set FRONTEND_ORIGIN=https://vibematch-xyz.vercel.app
```

(Use your actual Vercel URL from step 2, no trailing slash.) Setting a secret triggers an
automatic redeploy — no need to run `fly deploy` again for this one.

---

## 4. Verify end-to-end

Open the live Vercel URL in a browser and run a real search. If it fails, check in this order:

1. Browser console for a CORS error → means step 3 wasn't done or the URL doesn't match exactly
2. `fly logs` (from `backend/`) → shows backend-side errors (bad/missing API key, crash, etc.)
3. `fly secrets list` → confirms all 3 secrets (`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`,
   `FRONTEND_ORIGIN`) are actually set

---

## Future deploys

Backend: `fly deploy` from `backend/` after any change.
Frontend: automatic on every push to the connected GitHub branch (Vercel's default), or `vercel
--prod` manually if using the CLI flow.
