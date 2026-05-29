# IDMC MCP Server

Exposes Informatica Cloud Data Governance & Catalog (CDGC), Data Marketplace (CDMP),
and IDMC user/connection management APIs as MCP tools for use with any MCP-compatible
AI client (Claude Desktop, Claude Code, Cursor, etc.).

---

## Two modes of operation

| Mode | How credentials work | When to use |
|------|----------------------|-------------|
| **Local** | Read from `credentials.env` on disk | Personal dev / single user |
| **Container** | Encrypted in a per-user `X-IDMC-Token` header | Shared / multi-user deployment |

---

## Local mode (single user, no Docker)

Credentials live in a local file. The server runs as a stdio process — your MCP
client launches it directly.

### Prerequisites

- Python 3.10 or later
- An IDMC account with CDGC API access
- Your Informatica pod name (e.g. `dm-us`) — the prefix from your login URL:
  `https://<pod>.informaticacloud.com`

### Installation

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create your credentials file
cp credentials.env.example credentials.env
# Edit credentials.env and fill in pod, username, password

# 3. Test the server (starts silently — MCP uses stdio, Ctrl+C to stop)
python server.py
```

### Connect to Claude Code (local mode)

Add to `~/.claude/settings.json` (Windows: `%USERPROFILE%\.claude\settings.json`):

```json
{
  "mcpServers": {
    "idmc": {
      "command": "python",
      "args": ["C:/Tools/CDGC-MCP-Server/server.py"]
    }
  }
}
```

Run `/mcp` in Claude Code to reload. Optionally suppress per-call permission prompts:

```json
{
  "permissions": {
    "allow": ["mcp__idmc__*"]
  }
}
```

### Connect to Claude Desktop (local mode)

Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "idmc": {
      "command": "python",
      "args": ["C:/Tools/CDGC-MCP-Server/server.py"]
    }
  }
}
```

Restart Claude Desktop, then verify with: *"Which Snowflake catalog sources do I have?"*

---

## Container mode (shared / remote deployment)

The server runs as an HTTPS service. Credentials are **never stored on the server**
— each user enrolls once to receive an encrypted token, then includes that token in
every MCP request via the `X-IDMC-Token` header.

Rotating `ENCRYPTION_KEY` on the server immediately invalidates all existing tokens.

### Required environment variables

| Variable | Description |
|----------|-------------|
| `ENCRYPTION_KEY` | Fernet key used to encrypt/decrypt credential tokens |
| `ENROLL_PASSWORD` | Password required to access the `/enroll` page |

Generate an encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Step 1 — Enroll (get your token)

1. Open `https://<server>/enroll` in a browser
2. Enter the enrollment password (provided by the server administrator)
3. Enter your IDMC pod, username, and password
4. The page generates your token and ready-to-paste configs — copy and keep private

> Shortcut: `https://<server>/enroll?p=<password>` skips straight to the credentials form.
> You can share this URL with users to make setup easier.

### Step 2 — Connect to Claude Code (container mode)

Add to `~/.claude/settings.json` (Windows: `%USERPROFILE%\.claude\settings.json`):

```json
{
  "mcpServers": {
    "idmc": {
      "type": "http",
      "url": "https://<server>/mcp",
      "headers": {
        "X-IDMC-Token": "<your-token>"
      }
    }
  }
}
```

### Step 2 — Connect to Claude Desktop (container mode)

Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "idmc": {
      "type": "http",
      "url": "https://<server>/mcp",
      "headers": {
        "X-IDMC-Token": "<your-token>"
      }
    }
  }
}
```

> The enrollment page generates these configs for you with your actual token and server URL pre-filled.

---

## Running the container locally (Docker)

```bash
# Build the image
docker build -t idmc-mcp-server .

# Create your local env file (never committed to git)
cp container.env.example container.env
# Edit container.env — set ENCRYPTION_KEY and ENROLL_PASSWORD

# Run (env file stays on your machine, never enters the image)
docker run -d --name idmc-mcp-server --env-file container.env -p 8000:8000 idmc-mcp-server

# Or pass vars inline
docker run -d -e ENCRYPTION_KEY=xxx -e ENROLL_PASSWORD=secret -p 8000:8000 idmc-mcp-server
```

Enroll at `http://localhost:8000/enroll`. Use `http://` (not `https://`) for local Docker.

> `container.env` is a local convenience file — it is in `.gitignore` and never enters
> the image. In cloud deployments set the same variables via the platform secrets UI.

---

## Deploying to Google Cloud Run

Three steps: build locally → push to Artifact Registry → deploy.

```bash
# 1. Authenticate Docker with Artifact Registry (one-time per machine)
gcloud auth configure-docker us-central1-docker.pkg.dev

# 2. Create an Artifact Registry repo (one-time per GCP project)
gcloud artifacts repositories create idmc-mcp \
  --repository-format=docker \
  --location=us-central1 \
  --description="IDMC MCP Server"

# 3. Build the image locally
docker build -t idmc-mcp-server .

# 4. Tag and push to Artifact Registry
docker tag idmc-mcp-server \
  us-central1-docker.pkg.dev/<PROJECT_ID>/idmc-mcp/idmc-mcp-server:latest
docker push \
  us-central1-docker.pkg.dev/<PROJECT_ID>/idmc-mcp/idmc-mcp-server:latest

# 5. Deploy to Cloud Run
gcloud run deploy idmc-mcp-server \
  --image us-central1-docker.pkg.dev/<PROJECT_ID>/idmc-mcp/idmc-mcp-server:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --set-env-vars "ENCRYPTION_KEY=<your-key>,ENROLL_PASSWORD=<your-password>"
```

Replace `<PROJECT_ID>` with your GCP project ID.

- Cloud Run automatically provisions HTTPS — no certificate management needed
- The service scales to zero when idle — no cost while unused
- **To redeploy after code changes**, repeat steps 3–5 only

For production, use Google Secret Manager instead of `--set-env-vars`:
```bash
--set-secrets ENCRYPTION_KEY=idmc-encryption-key:latest,ENROLL_PASSWORD=idmc-enroll-password:latest
```

## Deploying to Azure Container Apps

```bash
az containerapp create \
  --name idmc-mcp-server \
  --resource-group <rg> \
  --image us-central1-docker.pkg.dev/<PROJECT_ID>/idmc-mcp/idmc-mcp-server:latest \
  --ingress external --target-port 8000 \
  --env-vars ENCRYPTION_KEY=secretref:encryption-key ENROLL_PASSWORD=secretref:enroll-password
```

---

## Troubleshooting

**`credentials.env must contain: pod, username, password`**
→ Local mode only. File is missing or has wrong key names — all lowercase: `pod`, `username`, `password`.

**`Login failed 401`**
→ Wrong username or password. Verify at `https://<pod>.informaticacloud.com`.

**`Login failed 404` or connection refused**
→ Wrong pod value. Check your IDMC login URL for the correct prefix.

**`X-IDMC-Token header is required`**
→ You are hitting the container server without a token. Enroll first at `/enroll`.

**`Invalid or expired token`**
→ The server's `ENCRYPTION_KEY` was rotated since your token was issued. Re-enroll.

**Too many failed attempts / frozen**
→ 3 wrong enrollment passwords triggers a 5-minute IP lockout. Wait and try again.

**Server connects but tool calls return errors**
→ Your IDMC user may not have CDGC API access. Contact your Informatica administrator.

**Claude Desktop / Claude Code doesn't show the server as connected (local mode)**
→ Verify the path in the config is correct and Python is on your PATH: `python --version`

---

## Notes

- The server automatically re-authenticates when the IDMC session token expires.
- Search query examples are in `query_examples.md` and are consulted automatically
  by the AI when building searches. Edit that file to add your own examples.
- Any MCP-compatible client works, not just Claude.
- Logs (container mode): `gcloud logging read "resource.labels.service_name=idmc-mcp-server" --limit=50`
- Live log tail: `gcloud beta logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=idmc-mcp-server"`
