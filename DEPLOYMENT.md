# Deployment Guide

Covers Docker and Railway deployment. For local dev without Docker, see
[README.md](./README.md).

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `HRMS_SECRET_KEY` | *(none — required)* | JWT signing key. Generate with `openssl rand -hex 32`. Never commit a real value. |
| `HRMS_DATABASE_URL` | `sqlite:///../data/hrms.db` | Or `postgresql://user:pass@host/dbname` |
| `HRMS_UPLOAD_DIR` | `../data/uploads` | Reserved for document storage — not wired up to an actual upload endpoint yet (blueprint §14 plans Cloudflare R2 for this). |
| `HRMS_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `HRMS_ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | JWT lifetime |

Copy `.env.example` to `.env` and fill in real values. `.env` is
gitignored — never commit it.

## Docker

The `Dockerfile` is a multi-stage build: it builds the frontend, then copies
the built assets and backend into a slim Python image. Both the container
and bare-metal dev use the same entrypoint, `startup.sh`, which detects
whether it's running inside Docker and skips the venv/npm-install steps
there since the image already has everything baked in.

```bash
# Build and run
docker-compose up -d

# One-time: seed the database
docker-compose exec app python -m app.seed

# Logs / stop
docker-compose logs -f app
docker-compose down
```

`docker-compose.yml` requires `HRMS_SECRET_KEY` to be set (via `.env` or
your shell environment) — it will refuse to start otherwise.

Access: API at `http://localhost:8020` (host port — the container itself
listens on 8000 internally), docs at `http://localhost:8020/docs`.

### Running the image directly (no compose)

```bash
docker build -t hrms:latest .
docker run -p 8020:8000 \
  -e HRMS_SECRET_KEY=$(openssl rand -hex 32) \
  -v $(pwd)/data:/data \
  hrms:latest
```

## Railway deployment

1. Push the repo to GitHub. Railway auto-detects the `Dockerfile`.
2. **New Project → Deploy from GitHub repo**, select this repo.
3. **Variables** — set at minimum:
   ```
   HRMS_SECRET_KEY=<openssl rand -hex 32>
   HRMS_DATABASE_URL=sqlite:////data/hrms.db
   HRMS_CORS_ORIGINS=https://your-railway-domain
   ```
4. **Volumes** — add a volume mounted at `/data` so the SQLite database
   survives redeploys. For production-grade Postgres instead, add Railway's
   PostgreSQL plugin and point `HRMS_DATABASE_URL` at it.
5. Push to `main` — Railway redeploys automatically. First deploy: run
   `python -m app.seed` once via the Railway terminal to create the initial
   HR Admin user and sample org structure.
6. Optional: **Settings → Domain → Add Custom Domain**, then add the CNAME
   Railway gives you at your DNS provider. SSL is automatic.

### Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails at build | Check `Dockerfile` is at repo root and `backend/requirements.txt` is valid |
| SQLite resets on every deploy | Volume isn't mounted at `/data` |
| CORS errors in the browser | `HRMS_CORS_ORIGINS` doesn't include the frontend's actual origin |

### Health check

Both the Dockerfile and Railway hit `GET /api/v1/health` to determine
container health.
