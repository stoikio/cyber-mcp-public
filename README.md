# Secure MCP Gateway

A security proxy that exposes **Gmail, Slack, Google Calendar, and Notion** to AI agents via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

Every tool call goes through a full security pipeline before reaching the backend API:

```
Authentication (JWT / API key) → Policy check (PG) → Rate limit (Redis) → Backend logic → Audit (PG + file)
```

## Features

- **OAuth2 + PKCE** — Google Workspace login with per-user token isolation
- **API key auth** — SHA-256 hashed keys with expiration and revocation
- **Policy engine** — configurable rules (block, warn, log) evaluated before each tool call
- **Rate limiting** — Redis-backed sliding window per user
- **Audit trail** — every action logged to PostgreSQL (+ optional file)
- **Sensitive email filtering** — blocks password resets, OTP codes, magic links from AI agents
- **Admin panel** — React SPA + FastAPI backend for managing policies, keys, integrations
- **Docker-ready** — multi-stage Dockerfile with PostgreSQL 17 + Redis 8

## Quick start

### 1. Prerequisites

- Python 3.11+
- Node.js 22+ (for admin frontend build)
- Docker & Docker Compose (for PostgreSQL + Redis)

### 2. Setup

```bash
# Clone the repo
git clone https://github.com/stoikio/cyber-mcp-public.git
cd cyber-mcp-public

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements_mcp.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings (GOOGLE_CLIENT_ID, JWT_SECRET, etc.)
```

### 3. Start infrastructure

```bash
docker compose up -d   # PostgreSQL + Redis
```

### 4. Initialize database

```bash
alembic upgrade head          # Run migrations
python3 seed_policies.py      # Load default security policies
```

### 5. Create an API key

```bash
python3 migrate_security.py --generate-encryption-key  # Add ENCRYPTION_KEY to .env
python3 migrate_security.py --generate-jwt-secret       # Add JWT_SECRET to .env
python3 migrate_security.py --add-key your-email@example.com
```

### 6. Start the gateway

```bash
python3 mcp_secure_gateway.py
# Gateway available at http://localhost:8000/mcp
```

### 7. Connect from Claude Desktop

```json
{
  "mcpServers": {
    "secure-mcp-gateway": {
      "url": "http://localhost:8000/mcp",
      "headers": { "X-API-Key": "YOUR_API_KEY" }
    }
  }
}
```

Or run `./setup_claude_desktop.sh` for automatic configuration.

## Docker deployment

```bash
# Build the image
docker build -t secure-mcp-gateway .

# Run (adjust env vars as needed)
docker run -p 8000:8000 -p 8001:8001 \
  --env-file .env \
  -e ENABLE_ADMIN=true \
  secure-mcp-gateway
```

The entrypoint automatically runs migrations, seeds policies, and starts the gateway.

## Admin panel

The admin panel provides a web UI for managing:

- Security policies (create, edit, toggle)
- API keys (create, revoke, list)
- Blocked email patterns
- Slack channel configurations
- Integration tokens (Slack, Notion)
- OAuth clients
- Audit log viewer
- Dashboard with usage stats

### Run locally

```bash
./start_admin.sh
# Admin panel at http://localhost:8001
```

### Run in Docker

Set `ENABLE_ADMIN=true` in your environment to start the admin panel alongside the gateway.

## MCP Tools (15 tools)

### Gmail (5)

| Tool | Description |
|------|-------------|
| `read_inbox` | Read recent emails (sensitive emails auto-filtered) |
| `read_email` | Read a specific email by ID |
| `search_emails` | Search emails with Gmail query syntax |
| `create_draft` | Create a Gmail draft (human-in-the-loop) |
| `send_email` | Send an email (blocked by default policy) |

### Slack (4)

| Tool | Description |
|------|-------------|
| `send_slack_dm` | Send a direct message to a user |
| `send_slack_message` | Send a message to a channel (blocked by default policy) |
| `list_slack_channels` | List available Slack channels |
| `read_slack_channel` | Read messages from a channel |

### Google Calendar (3)

| Tool | Description |
|------|-------------|
| `list_calendar_events` | List events for a date range |
| `check_availability` | Check available time slots |
| `create_calendar_event` | Create an event with attendees |

### Notion (3)

| Tool | Description |
|------|-------------|
| `notion_search` | Search pages and databases |
| `notion_read_page` | Read a page's content |
| `notion_query_database` | Query a database with filters |

> `send_email` and `send_slack_message` are blocked by default policies — use `create_draft` and `send_slack_dm` for safer alternatives.

## Security policies

Default policies include:

- Block direct email sending (force draft workflow)
- Warn on external recipients
- Block sensitive data in message bodies (passwords, API keys, private keys)
- Filter sensitive emails (password resets, OTP codes, magic links)
- Block automated recipient patterns (prevent agent loops)
- Cap result counts and date ranges
- Audit all tool calls

Edit policies via the admin panel or directly in `policies.json`.

## Project structure

```
├── mcp_secure_gateway.py       # MCP gateway entrypoint
├── gateway/                    # Core Python package
│   ├── config.py               # Environment configuration
│   ├── db.py                   # SQLAlchemy models + async engine
│   ├── crypto.py               # Fernet encryption helpers
│   ├── redis_client.py         # Async Redis client
│   ├── auth/                   # JWT, middleware, OAuth2 flow
│   ├── security/               # Policies, audit, rate limiting
│   ├── backends/               # Gmail, Slack, Calendar, Notion adapters
│   └── tools/                  # MCP tool registrations
├── admin/                      # Admin panel
│   ├── backend/                # FastAPI REST API
│   └── frontend/               # React + Vite + Tailwind SPA
├── alembic/                    # Database migrations
├── policies.json               # Default security policies
├── requirements_mcp.txt        # Python dependencies
├── Dockerfile                  # Container build
├── docker-compose.yaml         # Local PostgreSQL + Redis
└── .env.example                # Environment variable template
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ENCRYPTION_KEY` | Yes | Fernet key for token encryption |
| `JWT_SECRET` | Yes (prod) | HMAC secret for JWT signing |
| `GOOGLE_CLIENT_ID` | For OAuth | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | For OAuth | Google OAuth 2.0 client secret |
| `GATEWAY_DOMAIN` | For OAuth | Public domain for OAuth callbacks |
| `ALLOWED_EMAIL_DOMAIN` | Optional | Restrict login to a domain |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `ADMIN_EMAILS` | For admin | Comma-separated admin email list |
| `DEV_MODE` | No | Skip auth (dev only, **never** in prod) |

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
