# Production Deployment Guide — Forge AI

This guide provides end-to-end instructions for deploying **Forge AI** to production environments with high availability, isolated background workers, and cryptographic security.

---

## 1. System Architecture

```text
[ Internet / Clients ]
         │
         ▼
[ Reverse Proxy / Ingress / Cloudflare (HTTPS) ]
    ├──► https://app.forgeai.dev ──► [ Next.js 15 Standalone Frontend (Port 3000) ]
    └──► https://api.forgeai.dev ──► [ FastAPI Backend (Uvicorn Multi-Worker, Port 8000) ]
                                              │
                      ┌───────────────────────┼──────────────────────┐
                      ▼                       ▼                      ▼
        [ PostgreSQL 16 + pgvector ]      [ Redis 7 ]       [ ARQ Background Worker ]
```

---

## 2. Generating Production Secrets

Before deploying, generate cryptographically secure values for the required security keys:

```bash
# 1. JWT Secret (min 32 characters)
openssl rand -base64 48

# 2. AES-256-GCM Encryption Key (must be exactly 64 hex characters / 32 bytes)
openssl rand -hex 32

# 3. GitHub Webhook Secret
openssl rand -hex 32
```

> [!WARNING]
> In `ENVIRONMENT=production`, Forge AI strictly verifies that default or weak keys are not in use. The backend will refuse to boot if defaults are detected.

---

## 3. Deployment with Docker Compose (VPS / Cloud VM)

For deployment on a dedicated VM (AWS EC2, Hetzner, DigitalOcean, Linode):

### Step 1: Clone Repository & Create `.env`

```bash
git clone https://github.com/your-org/ForgeAi.git
cd ForgeAi
cp .env.production.example .env
```

Edit `.env` and fill in:
- `JWT_SECRET`, `ENCRYPTION_KEY`, and `GITHUB_WEBHOOK_SECRET`
- `POSTGRES_PASSWORD` and `DATABASE_URL`
- `BACKEND_CORS_ORIGINS=["https://app.yourdomain.com"]`
- `FRONTEND_URL=https://app.yourdomain.com`
- `NEXT_PUBLIC_API_URL=https://api.yourdomain.com`
- Your GitHub App credentials and LLM provider keys (`GROQ_API_KEY` or `GEMINI_API_KEY`)

### Step 2: Build & Start Services

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

This runs:
1. `postgres` (with `pgvector/pgvector:pg16`) & `redis`
2. `migration`: Runs `alembic upgrade head` and exits 0 upon completion
3. `api`: Starts Uvicorn with multiple worker processes once migrations succeed
4. `worker`: Starts ARQ consumer process for async indexing and repo analysis
5. `frontend`: Next.js production standalone server with `/api/health` monitoring

### Step 3: Verify Deployment Health

```bash
# Check container status
docker compose -f docker-compose.prod.yml ps

# Check API health
curl -f https://api.yourdomain.com/api/v1/health

# Check Frontend health
curl -f https://app.yourdomain.com/api/health
```

---

## 4. Managed Cloud Deployment (Render / Railway / Supabase / AWS)

If using managed cloud services:

### 1. Database & Cache
- **PostgreSQL**: Provision a managed PostgreSQL 16 database with the `vector` extension enabled (e.g. AWS RDS, Supabase, Neon).
- **Redis**: Provision Redis 7 (e.g. Upstash, AWS ElastiCache, Railway Redis).

### 2. Pre-Deployment Migration Job
Set the pre-deploy command on your backend service:
```bash
alembic upgrade head
```

### 3. Backend API Service
- **Build Command**: `pip install .`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 4`
- **Healthcheck Path**: `/api/v1/health`

### 4. ARQ Background Worker Service
- **Start Command**: `python -m arq app.workers.main.WorkerSettings`

### 5. Frontend Service
- **Build Command**: `npm run build`
- **Start Command**: `npm run start` (or `node server.js` if running standalone image)
- **Build Environment Variable**: `NEXT_PUBLIC_API_URL=https://your-backend-api.com`
- **Healthcheck Path**: `/api/health`

---

## 5. Production Security Checklist

- [ ] **HTTPS / TLS**: Reverse proxy (Nginx, Traefik, Caddy, or Cloudflare) terminates TLS 1.3.
- [ ] **Firewall**: PostgreSQL (`5432`) and Redis (`6379`) ports are closed to the public internet.
- [ ] **Security Headers**: HSTS, `X-Content-Type-Options: nosniff`, and `X-Frame-Options: DENY` are enabled.
- [ ] **Secrets Isolation**: No `.env` or `.pem` files are checked into version control or copied into Docker image layers.
- [ ] **CORS Restrictions**: `BACKEND_CORS_ORIGINS` explicitly lists only your frontend production domains.
- [ ] **Database Backups**: Automated daily snapshots enabled on PostgreSQL volume or managed provider.
