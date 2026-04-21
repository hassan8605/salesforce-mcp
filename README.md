# Salesforce MCP Server

A production-ready, multi-tenant **Model Context Protocol (MCP)** server for Salesforce built with Python, FastAPI, and Docker. Connect any Salesforce org via OAuth 2.0 and query it using natural language — powered by Claude AI.

---

## What This Does

- **MCP Server** — exposes 8 Salesforce tools over SSE so Claude Desktop (or any MCP client) can interact with Salesforce directly in conversation
- **Multi-tenant OAuth** — every user authenticates their own Salesforce org independently; data is fully isolated per user
- **NLP Query Endpoint** — send plain-English questions like _"show me my top 10 accounts"_ and Claude figures out the SOQL, runs it, and returns a human-readable answer
- **Full CRUD** — create, read, update, delete records across any standard or custom Salesforce object
- **Metadata Access** — inspect Apex classes, flows, validation rules, custom objects, layouts

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Docker Container                             │
│                                                                  │
│  FastAPI App (port 8000)                                         │
│  ├── /api/auth/*        OAuth 2.0 Web Server Flow               │
│  ├── /api/health/*      Connectivity checks                      │
│  ├── /api/salesforce/*  NLP query endpoint (Claude agentic loop) │
│  └── /mcp/sse           MCP Server (SSE transport)              │
│       └── UserIDMiddleware → reads ?user_id= from SSE URL        │
│                                                                  │
│  tokens/                                                         │
│  ├── alice.json         Alice's OAuth tokens + instance_url      │
│  ├── bob.json           Bob's OAuth tokens + instance_url        │
│  └── state_XYZ.json     CSRF state files (10-min TTL)           │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
  Salesforce Org A              Salesforce Org B
  (alice's company)             (bob's company)
```

Each user's `instance_url` is stored with their tokens, so API calls go directly to their specific Salesforce org — completely isolated.

---

## Tech Stack

| Component | Library |
|---|---|
| Web framework | FastAPI |
| MCP server | FastMCP (SSE transport) |
| Salesforce client | simple-salesforce |
| AI / NLP loop | Anthropic SDK (Claude) |
| HTTP client | httpx |
| Settings | pydantic-settings |
| Logging | structlog |
| Package manager | uv |
| Runtime | Docker + uvicorn |

---

## MCP Tools

| Tool | Description |
|---|---|
| `query` | Execute any SOQL query with auto-pagination |
| `tooling_query` | Tooling API queries (Apex, custom fields) |
| `describe_object` | Schema metadata for any object |
| `metadata_retrieve` | Retrieve Apex classes, Flows, Layouts, etc. |
| `get_record` | Fetch a single record by ID |
| `create_record` | Create a new record |
| `update_record` | Update fields on an existing record |
| `delete_record` | Permanently delete a record |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [ngrok](https://ngrok.com/) (free account, for OAuth callback during development)
- A Salesforce Developer Edition org — sign up free at [developer.salesforce.com](https://developer.salesforce.com/signup)
- An [Anthropic API key](https://console.anthropic.com/)

---

## Part 1 — Create a Salesforce Connected App

This is the most critical step. You must create a **Classic Connected App** — NOT an External Client App. This distinction matters:

| App Type | Distribution Options | Multi-org OAuth |
|---|---|---|
| External Client App (new UI) | Local / Packaged only | Only your org |
| **Classic Connected App** | **Local / Global** | **Any Salesforce org** |

### Step 1.1 — Navigate to the Classic Connected App form

In your Salesforce Developer Edition, open this URL directly in your browser (replace your domain):

```
https://YOUR-ORG.develop.my.salesforce.com/app/mgmt/forceconnectedapps/forceAppEdit.apexp
```

**OR** navigate there manually using Salesforce Classic view:

1. Click **Setup** (gear icon top right)
2. In Quick Find (left sidebar), type `connected`
3. Under **Apps → Connected Apps**, click **Manage Connected Apps**
4. You will see a list — but to create a new one, you need the URL above or follow Step 1.1 alt below

**Step 1.1 Alt** — Access via App Manager:
1. Setup → Quick Find → type `app manager`
2. Click **App Manager**
3. Do NOT click "New External Client App" — instead, use the direct URL above to get the classic form

### Step 1.2 — Fill in Basic Information

```
Connected App Name:  Salesforce MCP
API Name:            Salesforce_MCP    (auto-filled, leave as-is)
Contact Email:       your@email.com
Contact Phone:       optional
```

### Step 1.3 — Enable OAuth Settings

Scroll down to **API (Enable OAuth Settings)** section and check **Enable OAuth Settings**.

The form expands. Fill it as follows:

**Callback URL:**
```
https://YOUR_NGROK_URL/api/auth/callback
```
> You will update this after starting ngrok. For now enter a placeholder.

**Checkboxes:**
```
Enable for Device Flow:                          ☐ (leave unchecked)
Use digital signatures:                          ☐ (leave unchecked)
Require Proof Key for Code Exchange (PKCE):      ☐ UNCHECK THIS
Require Secret for Web Server Flow:              ☑ keep checked
Require Secret for Refresh Token Flow:           ☑ keep checked
Enable Client Credentials Flow:                  ☐ (leave unchecked)
Enable Authorization Code and Credentials Flow:  ☐ (leave unchecked)
```

> **PKCE must be unchecked.** This server uses the standard Authorization Code flow with a client secret. Enabling PKCE will cause token exchange to fail.

**Selected OAuth Scopes** — from the Available list, add these three:

```
Manage user data via APIs (api)
Perform requests at any time (refresh_token, offline_access)
Access the identity URL service (id, profile, email, address, phone)
```

Select each one in the left list → click **Add** to move it to the right.

Click **Save** → then **Continue** on the next page.

### Step 1.4 — Set Permitted Users (allow any org)

On the app detail page, click the **Manage** button (top of page), then click **Edit Policies**:

```
Permitted Users:  All users may self-authorize  ← change to this
IP Relaxation:    Relax IP restrictions         ← change to this
```

Click **Save**.

### Step 1.5 — Get Your Credentials

Back on the app detail page, click **Manage Consumer Details** (may require email verification code):

```
Consumer Key    →  copy this entire string  (→ SF_CLIENT_ID in .env)
Consumer Secret →  copy this entire string  (→ SF_CLIENT_SECRET in .env)
```

The Consumer Key looks like: `3MVG97L7PWbPq6UxXJL0cwCI...` (very long alphanumeric string).

---

## Part 2 — Project Setup

### Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/salesforce-mcp.git
cd salesforce-mcp
```

### Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
# ─── Application ──────────────────────────────────────────────
APP_HOST=0.0.0.0
APP_PORT=9856
ENVIRONMENT=development

# ─── Salesforce OAuth ─────────────────────────────────────────
# Use https://login.salesforce.com for Developer Edition / production
# Use https://test.salesforce.com for Sandbox orgs
SF_LOGIN_URL=https://login.salesforce.com

SF_CLIENT_ID=3MVG97L7PWbPq6Ux...your consumer key...
SF_CLIENT_SECRET=ABC123...your consumer secret...

# Must exactly match the Callback URL set in the Connected App
SF_REDIRECT_URI=https://YOUR_NGROK_URL/api/auth/callback

# ─── Token Storage ─────────────────────────────────────────────
SF_TOKENS_DIR=./tokens

# ─── Anthropic ─────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-...your key...
ANTHROPIC_MODEL=claude-sonnet-4-6
```

---

## Part 3 — Start ngrok

ngrok creates a public HTTPS URL that tunnels to your local server. Salesforce needs this to redirect back to you after the OAuth login.

```bash
ngrok http 9856
```

Output:
```
Forwarding  https://6a77-103-225-223-222.ngrok-free.app → http://localhost:9856
```

**Now do two things with the ngrok URL:**

**1. Update `.env`:**
```env
SF_REDIRECT_URI=https://6a77-103-225-223-222.ngrok-free.app/api/auth/callback
```

**2. Update the Callback URL in Salesforce:**
```
Setup → App Manager → Salesforce MCP → Edit
→ Callback URL: https://6a77-103-225-223-222.ngrok-free.app/api/auth/callback
→ Save
```

> **Important:** Free ngrok URLs change every time ngrok restarts. Each restart requires updating both places above and restarting Docker.

---

## Part 4 — Run with Docker

```bash
docker-compose up --build
```

Verify the server is healthy:
```bash
curl http://localhost:9856/health
# {"status": "healthy", "version": "2.0.0", "service": "salesforce-mcp"}
```

Interactive API docs:
```
http://localhost:9856/docs
```

---

## Part 5 — Connect Your Salesforce Org

### Authenticate

Open this URL in your **browser** (not curl, not Swagger — must be a real browser because it redirects to Salesforce login):

```
https://YOUR_NGROK_URL/api/auth/start?user_id=alice
```

What happens:
1. Server generates a CSRF state token → saves `tokens/state_XYZ.json`
2. Browser redirects to `login.salesforce.com`
3. You log in with your Salesforce credentials → click **Allow**
4. Salesforce redirects back to your callback URL
5. Server exchanges the code for tokens → saves `tokens/alice.json`
6. Browser shows:

```json
{
  "data": {"user_id": "alice", "connected": true},
  "message": "Salesforce connected successfully for user 'alice'."
}
```

### Verify the connection

```bash
curl "https://YOUR_NGROK_URL/api/health/salesforce?user_id=alice"
```

```json
{
  "connected": true,
  "username": "alice@yourcompany.com",
  "org_id": "00D5g000000XxXxEAK",
  "display_name": "Alice Smith",
  "instance_url": "https://yourcompany.my.salesforce.com"
}
```

---

## Part 6 — Test Queries

### NLP queries (plain English → Claude → SOQL → result)

```bash
# Count records
curl -X POST https://YOUR_NGROK_URL/api/salesforce/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "how many accounts do I have?"}'

# List recent contacts
curl -X POST https://YOUR_NGROK_URL/api/salesforce/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "show me the last 5 contacts created"}'

# Create a record
curl -X POST https://YOUR_NGROK_URL/api/salesforce/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "create a contact named John Doe with email john@acme.com"}'

# Open opportunities
curl -X POST https://YOUR_NGROK_URL/api/salesforce/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "list my open opportunities sorted by close date"}'

# Inspect schema
curl -X POST https://YOUR_NGROK_URL/api/salesforce/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "what fields does the Opportunity object have?"}'

# Update a record
curl -X POST https://YOUR_NGROK_URL/api/salesforce/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "update the account named Acme to set phone to 555-1234"}'
```

### Verify results in Salesforce UI

Log into your Salesforce org → **App Launcher** (grid icon top left) → search **Contacts** or **Accounts** to see records created via the API.

---

## Part 7 — Multi-Tenant Testing

The server supports unlimited users from different orgs simultaneously with full data isolation.

### Connect a second user

Send this URL to your friend/colleague (they open it in their browser):
```
https://YOUR_NGROK_URL/api/auth/start?user_id=bob
```

They log into **their own Salesforce org** — could be a completely different company. Their tokens are saved to `tokens/bob.json` with their org's `instance_url`.

### Verify data isolation

```bash
# Alice's org data
curl -X POST https://YOUR_NGROK_URL/api/salesforce/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "message": "how many contacts do I have?"}'

# Bob's org data (different number, different org)
curl -X POST https://YOUR_NGROK_URL/api/salesforce/query \
  -H "Content-Type: application/json" \
  -d '{"user_id": "bob", "message": "how many contacts do I have?"}'

# Verify different orgs via health check
curl "https://YOUR_NGROK_URL/api/health/salesforce?user_id=alice"
curl "https://YOUR_NGROK_URL/api/health/salesforce?user_id=bob"
# Should show different usernames, org_ids, and instance_urls
```

---

## Part 8 — Claude Desktop Integration (MCP)

Add to your Claude Desktop config file:

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

**Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "salesforce": {
      "url": "http://localhost:9856/mcp/sse?user_id=alice",
      "transport": "sse"
    }
  }
}
```

Restart Claude Desktop. You can now talk to Claude and it will query your Salesforce org directly:

> _"Show me all my accounts in California"_
> _"Create a new lead for Jane Smith at Acme Corp with title VP of Sales"_
> _"What's the total pipeline value of open opportunities closing this quarter?"_
> _"Show me the Apex class named AccountTriggerHandler"_

### Multiple users in Claude Desktop

```json
{
  "mcpServers": {
    "salesforce-alice": {
      "url": "http://localhost:9856/mcp/sse?user_id=alice",
      "transport": "sse"
    },
    "salesforce-bob": {
      "url": "http://localhost:9856/mcp/sse?user_id=bob",
      "transport": "sse"
    }
  }
}
```

---

## API Reference

### Auth Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/auth/start?user_id=X` | Start OAuth — **open in browser** |
| `GET` | `/api/auth/callback` | OAuth callback — Salesforce redirects here automatically |
| `GET` | `/api/auth/status?user_id=X` | Check if user is connected |
| `DELETE` | `/api/auth/disconnect?user_id=X` | Remove stored tokens and evict client |

### Health Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Basic server liveness check |
| `GET` | `/api/health/salesforce?user_id=X` | Deep Salesforce connectivity check (hits live API) |

### Salesforce Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/salesforce/query` | NLP query via Claude agentic loop |

**NLP Query request body:**
```json
{
  "user_id": "alice",
  "message": "show me my top accounts by annual revenue",
  "timezone": "UTC"
}
```

**Response:**
```json
{
  "answer": "Here are your top 5 accounts by annual revenue: ...",
  "tool_calls_made": ["query"],
  "iterations": 2
}
```

### MCP SSE Endpoint

```
GET /mcp/sse?user_id=alice
```

---

## Project Structure

```
salesforce-mcp/
├── main.py                    # FastAPI app, MCP mount, UserIDMiddleware
├── pyproject.toml             # Dependencies (uv)
├── Dockerfile                 # Multi-stage build
├── docker-compose.yml         # Service definition + token volume
├── .env.example               # Environment variable template
└── src/
    ├── settings.py            # Pydantic settings from .env
    ├── context.py             # ContextVar for per-request user_id injection
    ├── response.py            # Standardized JSON response helpers
    ├── schemas.py             # Request/response Pydantic models
    ├── auth/
    │   ├── oauth.py           # OAuth URL builder + callback handler
    │   ├── token_manager.py   # Token + CSRF state storage, auto-refresh
    │   └── router.py          # /api/auth/* endpoints
    ├── salesforce/
    │   ├── client.py          # Per-user Salesforce client factory (cached)
    │   ├── tools.py           # SOQL, CRUD, metadata tool implementations
    │   ├── service.py         # Claude agentic loop for NLP queries
    │   └── router.py          # /api/salesforce/* endpoints
    ├── mcp_server/
    │   └── server.py          # FastMCP tool definitions (SSE transport)
    └── health/
        └── router.py          # Health check endpoints
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SF_LOGIN_URL` | Yes | `https://login.salesforce.com` or `https://test.salesforce.com` |
| `SF_CLIENT_ID` | Yes | Connected App Consumer Key |
| `SF_CLIENT_SECRET` | Yes | Connected App Consumer Secret |
| `SF_REDIRECT_URI` | Yes | Must exactly match Callback URL in Connected App |
| `SF_TOKENS_DIR` | Yes | Directory for per-user token JSON files |
| `ANTHROPIC_API_KEY` | Yes | For NLP query endpoint |
| `ANTHROPIC_MODEL` | No | Default: `claude-sonnet-4-6` |
| `APP_HOST` | No | Default: `0.0.0.0` |
| `APP_PORT` | No | Default: `8000` |

---

## How OAuth Works

```
User opens browser:
  GET /api/auth/start?user_id=alice

Server:
  1. Generates CSRF state token (32-byte random)
  2. Saves tokens/state_XYZ.json { user_id, expires_at: now+10min }
  3. Redirects browser → login.salesforce.com/services/oauth2/authorize

User logs into Salesforce → clicks Allow

Salesforce redirects back:
  GET /api/auth/callback?code=ABC&state=XYZ

Server:
  1. Loads + deletes tokens/state_XYZ.json → gets user_id=alice
  2. Validates state not expired (10-min TTL)
  3. POSTs to Salesforce: exchanges authorization code for tokens
  4. Saves tokens/alice.json:
     { access_token, refresh_token, instance_url, token_type, scope }

All future API calls for alice:
  1. Load tokens/alice.json
  2. Test validity via GET {instance_url}/services/oauth2/userinfo
  3. Auto-refresh if 401 (access token expired, uses refresh_token)
  4. Build Salesforce client pointing to alice's instance_url
  5. Execute → return alice's data only
```

---

## Common Issues and Fixes

### `invalid_client_id` error on Salesforce login page

The `SF_CLIENT_ID` in `.env` doesn't match the Connected App.

**Fix:**
1. Salesforce Setup → App Manager → Salesforce MCP → View → Manage Consumer Details
2. Copy the full Consumer Key (it's a very long string, easy to truncate)
3. Paste into `SF_CLIENT_ID` in `.env` — ensure no spaces or line breaks
4. Restart Docker: `docker-compose down && docker-compose up`

### `OAUTH_EC_APP_NOT_FOUND` error

You created an **External Client App** instead of a Classic Connected App. External Client Apps restrict OAuth to users within your own org only.

**Fix:** Follow Part 1 to create a Classic Connected App using the direct URL:
```
https://YOUR-ORG.develop.my.salesforce.com/app/mgmt/forceconnectedapps/forceAppEdit.apexp
```

### `invalid_scope` error

The OAuth scope string contains `offline_access` which is not allowed in some Salesforce Connected App configurations.

**Fix:** The code already uses only `api refresh_token` — if you see this error, check your Connected App's Selected OAuth Scopes match the ones listed in Step 1.3.

### Swagger UI "Failed to fetch" on auth/start

Swagger UI blocks cross-origin redirects. The `/api/auth/start` endpoint returns a 307 redirect to Salesforce which Swagger can't follow.

**Fix:** Always test auth by opening the URL directly in your browser — never through Swagger.

### Friend still gets `OAUTH_EC_APP_NOT_FOUND`

1. Confirm you created a Classic Connected App (not External Client App)
2. Confirm Permitted Users = "All users may self-authorize"
3. Confirm the Callback URL in Salesforce exactly matches `SF_REDIRECT_URI` in `.env`
4. Restart Docker after any `.env` change

### Port confusion

If `APP_PORT=9856` in `.env`, the docker-compose maps it as `9856:8000` (host:container). Start ngrok pointing to the **host** port:

```bash
ngrok http 9856   # not ngrok http 8000
```

### Tokens lost after Docker restart

The `docker-compose.yml` uses a named Docker volume (`tokens:/app/tokens`) which persists across container restarts. However, if you run `docker-compose down -v` (with `-v` flag), volumes are deleted. Use `docker-compose down` without `-v` to keep tokens.

---

## Development (without Docker)

```bash
# Install uv package manager
pip install uv

# Create virtualenv and install dependencies
uv sync

# Run server with auto-reload
uv run python main.py
```

### Rebuild Docker after code changes

```bash
docker-compose down
docker-compose up --build
```

### View live logs

```bash
docker-compose logs -f salesforce-mcp
```

---

## Security Notes

- **Token storage:** Tokens are stored as JSON files on disk. For production, use AWS Secrets Manager, HashiCorp Vault, or an encrypted database column.
- **CSRF protection:** State tokens are written to disk with a 10-minute TTL and auto-purged after use — safe across server restarts unlike in-memory dicts.
- **Token volume:** The Docker volume persists tokens across container restarts without leaking them into the image.
- **Secrets in `.env`:** Never commit `.env` to git. The `.gitignore` should exclude it. Use `.env.example` as the committed template.
- **Production domains:** Replace ngrok with a real domain and valid TLS certificate. Update `SF_REDIRECT_URI` and the Connected App Callback URL accordingly.