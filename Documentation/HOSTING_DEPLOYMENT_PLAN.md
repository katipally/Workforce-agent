# Hosting Deployment Plan (Vercel + AWS EC2 + Supabase)

This document explains how to deploy the hosting version of Workforce Agent using the **Agent-Hosting-style** layout:

- **Frontend** (`frontend`) on **Vercel** (free Hobby plan).
- **Backend** (`backend`) on **AWS EC2** (free tier–eligible or small instance).
- **Database** on **Supabase** (already running, IPv6-only free tier considered).

The plan is written to work with the existing code **without refactoring** the Slack→Notion worker or other backend logic.

---

## 1. High-level architecture

- **Browser** → **Vercel (`frontend/`)**
  - Serves the built React app.
  - Uses `VITE_API_BASE_URL` to talk to the backend.
- **Vercel frontend** → **EC2 backend (`backend/`)**
  - All HTTP API calls go to `${VITE_API_BASE_URL}/...`.
  - WebSockets connect to `${VITE_API_BASE_URL}/api/chat/ws`.
- **EC2 backend** → **Supabase Postgres**
  - Uses `DATABASE_URL` from the project `.env` at the repo root.
  - Supabase free tier may be IPv6-only; we avoid Docker to prevent IPv6 issues.
- **EC2 backend** → Slack / Notion / other APIs
  - Uses tokens from the same `.env`.

Key code connections:

- Frontend base URL: `frontend/src/lib/api.ts` uses `VITE_API_BASE_URL`.
- WebSockets: `frontend/src/hooks/useWebSocket.ts` builds `wss://` URL from `API_BASE_URL`.
- Backend CORS: `backend/api/main.py` uses `Config.FRONTEND_BASE_URL` to allow the deployed frontend.
- Backend config: `backend/core/config.py` loads environment from the project `.env`.

---

## 2. Prerequisites

Before deploying, ensure you have:

- **Git repository** containing this project (including `Hosting/` folder).
- **Supabase project**:
  - Note the **connection string** for your database.
  - Confirm it works from a non-Docker IPv6-capable host.
- **Slack app and tokens** (at least `SLACK_BOT_TOKEN`).
- **Notion integration**:
  - `NOTION_TOKEN` (internal integration token).
  - `NOTION_PARENT_PAGE_ID` for the workspace page where Slack feeds will be created.
- **OpenAI API key** (if you use the AI/chat features).
- **AWS account** (for EC2).
- **Vercel account** (GitHub/GitLab/Bitbucket integration is easiest).

Optional:

- A **custom domain** (not required; Vercel's default domain works fine), e.g.:
  - `app.example.com` for the frontend (Vercel).
  - `api.example.com` for the backend (EC2 + Nginx).

---

## 3. Environment variables overview

### 3.1 Backend environment (`.env` at project root)

Create a `.env` file at the **project root** (`.env`). `Config` in `backend/core/config.py` loads this for the backend.

Below is the **full template** (required + optional) matching `Hosting/.env.example`. For a complete, fully featured deployment, copy this block and replace every placeholder.

```env
# ============================================================================
# SLACK CONFIGURATION
# ============================================================================

# Slack API Tokens (Required)
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here

# Slack App Credentials (from App Credentials page)
SLACK_APP_ID=your-app-id-here
SLACK_CLIENT_ID=your-client-id-here
SLACK_CLIENT_SECRET=your-client-secret-here
SLACK_SIGNING_SECRET=your-signing-secret-here
SLACK_VERIFICATION_TOKEN=your-verification-token-here

# SLACK_MODE can be: read_only, standard, admin
SLACK_MODE=standard
# Comma-separated channel names or IDs (without #) that are read-only or blocked
SLACK_READONLY_CHANNELS=
SLACK_BLOCKED_CHANNELS=

# ============================================================================
# NOTION CONFIGURATION
# ============================================================================

# Notion API (for exporting to Notion and Slack→Notion workflows)
NOTION_TOKEN=secret_your_notion_token
NOTION_PARENT_PAGE_ID=your-parent-page-id

# Notion safety mode: standard or read_only
NOTION_MODE=standard

# ============================================================================
# GOOGLE OAUTH (login + per-user Gmail + Calendar)
# ============================================================================

# OAuth 2.0 Web client credentials from Google Cloud Console
GOOGLE_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret

# Base URL of your backend used in the OAuth redirect URI
# For local development this will usually be http://localhost:8000
# In production on EC2, use: https://api.your-domain.com
GOOGLE_OAUTH_REDIRECT_BASE=http://localhost:8000

# Base URL of your frontend app
# For local development this will usually be http://localhost:5173
# In production, set to your Vercel URL, e.g. https://your-frontend.vercel.app
FRONTEND_BASE_URL=http://localhost:5173

# Strong random string for signing session cookies and OAuth state
SESSION_SECRET=change-me-to-a-long-random-string

# ============================================================================
# DATABASE CONFIGURATION (Supabase in production)
# ============================================================================

# For local dev this may be a local Postgres URL.
# In production on EC2, use the Supabase connection string
# (e.g. postgresql://USER:PASSWORD@HOST:PORT/DATABASE?sslmode=require).
DATABASE_URL=postgresql://user:password@localhost:5432/workforce_agent

# Data storage paths (used for exports, files, etc.)
DATA_DIR=data
FILES_DIR=data/files
EXPORT_DIR=data/raw_exports
PROJECT_REGISTRY_FILE=data/project_registry.json

# Rate limiting (requests per minute)
TIER_4_RATE_LIMIT=100
DEFAULT_RATE_LIMIT=50

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/slack_agent.log

# Real-time streaming (Slack Socket Mode)
SOCKET_MODE_ENABLED=true
MAX_RECONNECT_ATTEMPTS=10

# Optional: Workspace info (used for labeling/config)
WORKSPACE_NAME=your-workspace
WORKSPACE_ID=T12345678

# ============================================================================
# OPENAI API (Required for AI Agent)
# ============================================================================

OPENAI_API_KEY=sk-your-openai-api-key

# ============================================================================
# AI AGENT CONFIGURATION (Optional)
# ============================================================================

# Model configuration
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
LLM_MODEL=gpt-5-nano

# Performance settings
EMBEDDING_BATCH_SIZE=32
USE_GPU=false

# API Server
API_PORT=8000
API_HOST=0.0.0.0

# ============================================================================
# GMAIL SAFE-SEND AND SCOPE
# ============================================================================

# Modes: draft (never send, only return drafts), confirm (default, requires confirmation), auto_limited
GMAIL_SEND_MODE=confirm

# Comma-separated domains allowed for sending (e.g. @company.com,@partner.com)
GMAIL_ALLOWED_SEND_DOMAINS=

# Comma-separated domains to scope read/search results (e.g. @company.com)
GMAIL_ALLOWED_READ_DOMAINS=

# Optional default Gmail label to scope advanced searches (e.g. Work/Projects)
GMAIL_DEFAULT_LABEL=Datasaur
```

For production:

- Replace all `your-...` placeholders with real values.
- Set `DATABASE_URL` to your **Supabase** Postgres URL (with `sslmode=require`).
- Set `FRONTEND_BASE_URL` to your Vercel production URL.
- Set `GOOGLE_OAUTH_REDIRECT_BASE` to your backend HTTPS URL (e.g. `https://api.example.com`).
- Use a long, random `SESSION_SECRET`.

### 3.2 Frontend (Vercel project env)

In Vercel project settings, you will set:

```env
VITE_API_BASE_URL=https://your-api-domain.com
```

- This must be the **public HTTPS base URL** of your EC2 backend.
- The frontend will then call, for example, `https://your-api-domain.com/api/workflows` and connect to `wss://your-api-domain.com/api/chat/ws`.

---

## 4. Deploying the backend to AWS EC2

### 4.1 Create an EC2 instance (Amazon Linux, free tier)

1. In the AWS console, go to **EC2 → Instances → Launch instance**.
2. Choose:
   - **Name**: `workforce-hosting-backend`.
   - **AMI**: **Amazon Linux 2023** (Amazon Linux AMI; free-tier eligible).
   - **Instance type**: `t2.micro` or `t3.micro` (AWS Free Tier includes up to **750 hours/month** of Linux `t2.micro`/`t3.micro` usage for the **first 12 months** of a new account, as long as you stay within free-tier limits).
3. Configure network (VPC, subnet, routing):
   - **VPC**: choose the **default VPC** (do not create a custom one for this simple setup).
   - **Subnet**: choose one of the default subnets in that VPC (it should already have a route `0.0.0.0/0 → igw-...` to an **Internet Gateway**, making it public).
   - **Auto-assign public IPv4 address**: set to **Enable** so the instance gets a public IPv4 address.
   - **IPv6**: you can leave this disabled, or enable it if your Supabase project requires IPv6; it is optional for most setups.
4. Network ACL (usually default):
   - Keep the default Network ACL, which **allows all inbound and outbound traffic**.
   - If you use a custom NACL, ensure it has `ALLOW` rules for inbound `HTTP (80)`/`HTTPS (443)` and outbound `0.0.0.0/0`.
5. Security group (instance firewall):
   - Allow **SSH (22)** from your IP (for example `x.x.x.x/32`).
   - Allow **HTTP (80)** from anywhere: `0.0.0.0/0` (IPv4) and optionally `::/0` (IPv6).
   - Allow **HTTPS (443)** from anywhere: `0.0.0.0/0` (IPv4) and optionally `::/0` (IPv6).
6. Create and download an SSH key pair (for example `Agent-Ec2-Keypair`).
   - Save the `.pem` file in a safe folder on your Mac (for example `~/Keys/Agent-Ec2-Keypair.pem`).
   - Do **not** open or edit the file in an editor; only use it for SSH.
   - You cannot re-download this key later. If it is lost or corrupted, create a new key pair and, if necessary, a new instance.
7. Launch the instance and note its **public IP / DNS name**.

### 4.2 SSH into the instance

From your local machine:

```bash
chmod 400 /Users/yashwanthreddy/Desktop/Host/Agent-Ec2-Keypair.pem

ssh -i /path/to/key.pem ec2-user@EC2_PUBLIC_DNS
```

Tips to avoid SSH key issues:
- Always run `chmod 400` on the `.pem` file so SSH accepts it.
- Do not email or sync the key file via insecure channels.
- If you see "UNPROTECTED PRIVATE KEY FILE" errors, re-run `chmod 400` and retry.

### 4.3 Install system dependencies (Python, Git, Nginx, Certbot)

Update packages and install base tools:

```bash
sudo dnf update -y
sudo dnf install -y python3 python3-pip git nginx augeas-libs
```

Set up **Certbot** in a dedicated virtualenv (recommended for Amazon Linux 2023):

```bash
# Create a virtualenv for Certbot
sudo python3 -m venv /opt/certbot
sudo /opt/certbot/bin/pip install --upgrade pip
sudo /opt/certbot/bin/pip install certbot certbot-nginx

# Make certbot available on PATH
sudo ln -s /opt/certbot/bin/certbot /usr/bin/certbot

# Enable and start Nginx
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl status nginx --no-pager -l
```

You will use `sudo certbot --nginx -d YOUR_API_DOMAIN` later, after the domain and Nginx are fully configured and reachable over HTTP.

### 4.4 Get your code onto the server

Option A – **Clone from Git**:

```bash
cd ~
git clone YOUR_REPO_URL Workforce-agent
cd Workforce-agent
```

Option B – **Upload via scp/rsync**: copy your local project to `~/Workforce-agent`.

The paths should match your current repo layout, e.g. `~/Workforce-agent/backend` and `~/Workforce-agent/frontend`.

### 4.5 Create Python virtualenv and install dependencies

```bash
cd ~/Workforce-agent
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# Use a larger temp directory so pip doesn't run out of /tmp space
mkdir -p ~/pip-tmp
export TMPDIR=/home/ec2-user/pip-tmp

# Install CPU-only torch (smaller wheel, suitable for t2.micro/t3.micro)
pip install --no-cache-dir torch==2.2.1 --index-url https://download.pytorch.org/whl/cpu

# Install backend dependencies
pip install --no-cache-dir -r backend/requirements.txt
```

> Note: This repository uses `backend/requirements.txt` for the hosting backend.

### 4.6 Create the `.env` file

On the server:

```bash
cd ~/Workforce-agent
nano .env
```

Paste the variables described in **Section 3.1**, using the real values for:

- `DATABASE_URL` from Supabase (copy the `psql` connection string, ensure `sslmode=require`).
- Slack, Notion, OpenAI keys.
- Temporarily set `FRONTEND_BASE_URL` to `http://localhost:5173` or leave the default; you will update it later to the final Vercel URL.

Save the file.

### 4.7 Test Supabase connectivity (IPv6, no Docker)

Because Supabase free tier can be IPv6-only, we **avoid Docker** and run directly on the host.

Optional direct test:

```bash
sudo dnf install -y postgresql
psql "DATABASE_URL_FROM_SUPABASE"
```

- If this connects successfully, your EC2 instance can reach Supabase.
- If it fails with network/IPv6 errors, verify that the VPC/subnet has IPv6 enabled and outbound internet access.

### 4.8 Run the backend manually for a quick test

```bash
cd ~/Workforce-agent
source .venv/bin/activate
cd backend
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

- From your local machine, open `http://EC2_PUBLIC_IP:8000/docs`.
- You should see the FastAPI Swagger UI.
- Create a test workflow or call `/api/workflows` to confirm DB connectivity.

If this works, your backend + Supabase + Slack/Notion tokens are correctly wired.

### 4.9 Create a systemd service for the backend

Stop the manual `uvicorn` process (`Ctrl+C`), then create a systemd unit:

```bash
sudo nano /etc/systemd/system/workforce-backend.service
```

Example content (adjust paths and user if needed):

```ini
[Unit]
Description=Workforce Hosting Backend (FastAPI)
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/Workforce-agent
Environment="PATH=/home/ec2-user/Workforce-agent/.venv/bin"
ExecStart=/home/ec2-user/Workforce-agent/.venv/bin/uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Reload and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable workforce-backend
sudo systemctl start workforce-backend
sudo systemctl status workforce-backend
```

- Confirm it shows as **active (running)**.
- Check `http://EC2_PUBLIC_IP:8000/docs` again.

This process also starts your Slack→Notion worker as before (the app’s startup code is unchanged).

### 4.10 Configure Nginx as reverse proxy (HTTP → backend)

On Amazon Linux, Nginx typically loads virtual host configs from `/etc/nginx/conf.d/`.

Create a config file (replace `api.your-domain.com` with your real API domain):

```bash
sudo nano /etc/nginx/conf.d/workforce-backend.conf
```

Example HTTP-only config (HTTPS will be added by Certbot):

```nginx
server {
    listen 80;
    server_name api.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support for /api/chat/ws
    location /api/chat/ws {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_pass http://127.0.0.1:8000;
    }
}
```

Test and reload Nginx:

```bash
sudo nginx -t
sudo systemctl restart nginx
```

Verify on the EC2 instance that Nginx is serving HTTP:

```bash
curl -I http://127.0.0.1
```

You should see an `HTTP/1.1 200` (or similar) response from Nginx.

### 4.11 Connect your domain to EC2 and enable HTTPS with Let’s Encrypt

Before running Certbot, complete these steps:

1. **Allocate and associate an Elastic IP (EIP)**  
   - EC2 → **Elastic IP addresses** → **Allocate Elastic IP address** (same region as the instance).  
   - After it is created, select it → **Actions → Associate Elastic IP address** → choose your backend instance → **Associate**.

2. **Create a DNS record for your API domain**  
   - At your DNS provider (Route 53 or external registrar), create an **A record**:  
     - Name: `api` (for `api.your-domain.com`)  
     - Type: `A`  
     - Value: the Elastic IP from step 1 (for example `3.x.x.x`).  
   - Wait a few minutes for DNS to propagate.

3. **Verify DNS from your local machine**  

   ```bash
   dig +short api.your-domain.com
   ```  

   This should print exactly your Elastic IP.

4. **Verify HTTP reachability**  
   - From the EC2 instance:

     ```bash
     curl -I http://api.your-domain.com
     ```  

   - From your local machine:

     ```bash
     curl -I http://api.your-domain.com
     ```  

   Both commands should return an HTTP status (200/301/404). If they time out, re-check:  
   - The security group allows **HTTP 80** from `0.0.0.0/0` (IPv4), not just `::/0`.  
   - The subnet’s route table has `0.0.0.0/0 → igw-...` (Internet Gateway).  
   - The Network ACL allows inbound/outbound HTTP.

5. **Request and install the certificate with Certbot**  

   ```bash
   sudo certbot --nginx -d api.your-domain.com
   ```  

   - Accept the Terms of Service.  
   - Choose the option to **redirect HTTP to HTTPS** when prompted.

Afterwards, you should be able to access:

- `https://api.your-domain.com/docs`
- WebSockets at `wss://api.your-domain.com/api/chat/ws`

This HTTPS endpoint will be used as `VITE_API_BASE_URL`.

### 4.12 Set `FRONTEND_BASE_URL` on the backend

Later, after the frontend is deployed on Vercel, set in `Hosting/.env`:

```env
FRONTEND_BASE_URL=https://your-frontend-url.vercel.app
```

Then reload the backend service:

```bash
sudo systemctl restart workforce-backend
```

This ensures CORS allows the frontend origin, and cookies/websockets work correctly.

---

## 5. Deploying the frontend to Vercel

### 5.1 Import the project to Vercel

1. Go to [https://vercel.com](https://vercel.com) and log in.
2. Click **New Project** → import your Git repository.
3. When asked for **framework** and **settings**:
   - **Root directory**: `frontend`
   - **Framework preset**: `Vite` (or `React` if Vercel suggests it).
   - **Build command**: `npm run build`
   - **Output directory**: `dist`

Vercel will detect `package.json` inside `frontend`.

### 5.2 Configure environment variable for API base URL

In the Vercel project settings → **Environment Variables**:

- Add:

  - **Name**: `VITE_API_BASE_URL`
  - **Value**: `https://api.example.com` (your EC2 backend HTTPS URL)
  - **Environment**: Production (and Preview if you want)

Redeploy the project so the env var is applied.

### 5.3 First deploy and test

1. Let Vercel complete the initial deployment.
2. Note the **Production URL**, e.g. `https://workforce-hosting.vercel.app`.
3. Open that URL in your browser:
   - The app should load.
   - Network tab should show requests to `https://api.example.com/api/...`.

If API calls fail with CORS errors:

- Ensure `FRONTEND_BASE_URL` in the backend `.env` matches exactly the deployed Vercel URL (including `https://`).
- Restart `workforce-backend` service after updating `.env`.

### 5.4 (Optional) Attach your own domain to the frontend

If you want to serve the frontend on a subdomain like `app.your-domain.com` instead of the default Vercel URL:

1. In the Vercel project, go to **Settings → Domains → Add** and add `app.your-domain.com`.  
2. Vercel will show the required DNS record. At your DNS provider, create:  
   - Type: `CNAME`  
   - Name: `app`  
   - Value: the Vercel-provided target (for example `cname.vercel-dns.com`).  
3. Wait for DNS to propagate, then verify in Vercel that the domain is **verified** and **primary**.  
4. If you switch to `https://app.your-domain.com` as the main frontend URL, also set:  
   - `FRONTEND_BASE_URL=https://app.your-domain.com` in `Hosting/.env`.  
   - Keep `VITE_API_BASE_URL=https://api.your-domain.com` in Vercel.  
5. Restart the backend service after changing `FRONTEND_BASE_URL`.

---

## 6. How frontend and backend connect (code-level)

This section summarizes how the existing code expects things to be wired.

### 6.1 Frontend → Backend (HTTP)

- `frontend/src/lib/api.ts`:

  ```ts
  export const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || 'http://localhost:8000'
  ```

- All API calls use `API_BASE_URL` prefix, e.g. in `authStore.ts`:

  ```ts
  fetch(`${API_BASE_URL}/auth/me`, { credentials: 'include' })
  ```

So as long as `VITE_API_BASE_URL` is set to `https://api.example.com`, all existing frontend code will target that backend.

### 6.2 Frontend → Backend (WebSocket)

- `frontend/src/hooks/useWebSocket.ts` constructs the WebSocket URL as:

  ```ts
  const wsBase = API_BASE_URL.startsWith('https')
    ? API_BASE_URL.replace(/^https/, 'wss')
    : API_BASE_URL.replace(/^http/, 'ws')

  const WS_URL = `${wsBase}/api/chat/ws`
  ```

With `VITE_API_BASE_URL=https://api.example.com`, this becomes `wss://api.example.com/api/chat/ws`, which is proxied by Nginx to uvicorn.

### 6.3 Backend CORS and frontend origin

- `backend/api/main.py` sets CORS origins based on `Config.FRONTEND_BASE_URL`:

  ```python
  _frontend_origins = ["http://localhost:5173", "http://localhost:3000"]
  if Config.FRONTEND_BASE_URL and Config.FRONTEND_BASE_URL not in _frontend_origins:
      _frontend_origins.append(Config.FRONTEND_BASE_URL)

  app.add_middleware(
      CORSMiddleware,
      allow_origins=_frontend_origins,
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

As long as `FRONTEND_BASE_URL` matches the Vercel production URL, CORS is correctly handled for both APIs and cookies.

### 6.4 Background worker

- The backend startup logic in `backend/api/main.py` starts the Slack→Notion scheduler thread when the app starts, and ties it to active workflows.
- Running under `uvicorn` on EC2 with the existing systemd service preserves this behavior; **no changes** are required for hosting.

---

## 7. IPv6 / Supabase notes

- Supabase’s free tier may expose a **host that prefers or requires IPv6**.
- When you run the backend **directly on EC2** (no Docker), the OS’s IPv6 stack can connect normally as long as:
  - Your VPC/subnet has IPv6 configured.
  - Outbound IPv6 is allowed.
- If you later choose to run the backend in Docker on EC2, you will need to ensure Docker is configured with **IPv6 networking and NAT**, which is more complex and can reintroduce the issue you saw locally.

This deployment plan intentionally avoids Docker for the backend, to keep connectivity with Supabase as simple and reliable as possible.

---

## 8. Final checklist

- [ ] EC2 instance (Amazon Linux) running, IPv6 enabled in VPC/subnet.
- [ ] Instance type is `t2.micro` or `t3.micro` and total monthly hours stay within the AWS Free Tier (750 hours/month for the first 12 months of a new account).
- [ ] Backend service (`workforce-backend`) active and serving `https://api.example.com/docs`.
- [ ] Supabase `DATABASE_URL` in `Hosting/.env` tested and working.
- [ ] Slack, Notion, OpenAI keys set in `Hosting/.env`.
- [ ] Nginx reverse proxy and Certbot configured; WebSocket path `/api/chat/ws` works over `wss://`.
- [ ] Vercel project created with root `Hosting/frontend` (Hobby plan, within free limits).
- [ ] `VITE_API_BASE_URL` set to your backend HTTPS URL.
- [ ] `FRONTEND_BASE_URL` in backend `.env` set to your Vercel URL; backend restarted.
- [ ] Frontend loads on Vercel, workflows and Slack→Notion sync work end-to-end.

## 9. Staying within AWS free tier and controlling costs (Nov 2025)

To keep costs effectively at **$0** during initial testing:

- Use a **single** `t2.micro` or `t3.micro` Amazon Linux instance and keep it running for at most **750 hours/month** (one instance running all month) during your first 12 months on AWS.
- Avoid creating extra EC2 instances or expensive services beyond this plan.

### 9.1 Create a monthly AWS budget

1. In the AWS console, go to **Billing & Cost Management → Budgets**.
2. Click **Create budget** → choose **Cost budget**.
3. Set:
   - **Period**: Monthly.
   - **Budgeting method**: Fixed.
   - **Budgeted amount**: e.g. `5` USD (or another low amount you’re comfortable with).
4. Add **alerts**:
   - One at **80%** of budget (forecasted or actual).
   - One at **100%** of budget.
   - Enter your **email address** (and/or SNS topic) for notifications.
5. Review and **Create budget**.

This ensures you get emails before you exceed your target spend.

### 9.2 (Optional) Automatically stop the EC2 instance at 100% budget

If you want AWS to take action (not just notify):

1. Edit the budget you created and add a **Budget action**.
2. Choose **Action type** for **EC2** and select your `workforce-hosting-backend` instance.
3. Configure the action to **Stop this instance** when the **100%** threshold is reached.
4. When prompted, allow AWS Budgets to create an **IAM role** that has permission to stop EC2 instances (follow the wizard defaults).
5. Save the action.

Now, if costs go above your budget, AWS can automatically stop the backend instance so charges don’t keep increasing.

### 9.3 Track free-tier usage

- In the **Billing** console, enable **Free Tier alerts** and **Billing alerts** in **Billing preferences**.
- Use **Cost Explorer** or the **Free Tier usage** page to verify that your EC2 usage stays within the free allowance.
- If you ever run more than one EC2 instance or use larger types, revisit this plan and your budget.

---

## 10. Teardown and starting over (optional)

If you want to completely remove the deployment and start from scratch, follow this order to avoid dangling dependencies and charges.

### 10.1 Remove DNS records for this app

1. At your domain registrar or Route 53 hosted zone, delete any records that point to the EC2 backend, such as:  
   - `A` record for `api.your-domain.com` → `3.x.x.x`.  
   - Any `app.your-domain.com` CNAMEs if you no longer want the frontend domain.  
2. Keep the root domain (`your-domain.com`) if you plan to reuse it later.

### 10.2 Release Elastic IP

1. AWS Console → **EC2 → Elastic IP addresses**.  
2. Select the Elastic IP used for the backend.  
3. **Actions → Disassociate Elastic IP address** (if associated).  
4. **Actions → Release Elastic IP address** to avoid charges.

### 10.3 Terminate the EC2 instance

1. EC2 → **Instances**.  
2. Select the backend instance (for example `workforce-hosting-backend`).  
3. **Instance state → Terminate instance** and confirm.  
4. Wait until its state becomes **terminated**.

### 10.4 Delete security groups and key pair used only for this app

1. EC2 → **Security Groups**:  
   - Find any custom security groups created for this backend (for example `launch-wizard-1`).  
   - Ensure they are **not attached** to any instances or ENIs, then **Delete** them.  
   - Do **not** delete the **default** security group.  
2. EC2 → **Key pairs**:  
   - Delete the key pair you created for this instance (for example `Agent-Ec2-Keypair`).  
   - Optionally delete the local `.pem` file on your machine.

### 10.5 (Optional) Remove custom networking resources

If you created **additional** VPCs, subnets, route tables, or Network ACLs specifically for this app:

1. Verify no subnets, ENIs, or instances still reference them.  
2. In **VPC → Subnets**, delete any unused custom subnets.  
3. In **VPC → Route tables**, delete unused custom route tables.  
4. In **VPC → Network ACLs**, delete unused custom NACLs.  

Do **not** delete the default VPC or its default subnets/route tables/NACLs unless you are sure you understand the consequences.

After this cleanup, you can follow this document again from Section 4 to create a fresh EC2 backend and reconnect your domain cleanly.
