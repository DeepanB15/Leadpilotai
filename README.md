# LeadPilotAI

LeadPilotAI is a Docker Compose project containing a PostgreSQL database, an n8n automation service, and three exported n8n workflows for database setup, lead intelligence, and lead uploads.

## Project Structure

- `docker/` - reserved for Docker-related files; currently empty.
- `docs/` - project documentation; currently empty.
- `prompts/` - prompt files; currently empty.
- `sql/` - standalone SQL scripts; currently empty. Database setup logic is present in the exported n8n workflow.
- `workflows/` - n8n workflow exports:
  - `database-setup.json` - manual-trigger workflow with a PostgreSQL node.
  - `lead-intelligence.json` - workflow using PostgreSQL, an HTTP request, and an Ollama chat model.
  - `upload-leads.json` - form submission, file extraction, and PostgreSQL workflow.
- `backups/` - local backup storage; intentionally excluded from Git.
- `docker-compose.yml` - starts PostgreSQL and n8n.
- `.env.example` - template for the Compose environment variables.
- `.env` - local environment settings; do not commit this file.

## Requirements

- Docker Desktop with Docker Compose on Windows, or Docker Engine with the Docker Compose plugin.

## Environment Setup

Create a local `.env` file from the template:

```powershell
Copy-Item .env.example .env
```

Or, in a shell that supports `cp`:

```sh
cp .env.example .env
```

Fill in the variables used by `docker-compose.yml`:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `N8N_BASIC_AUTH_ACTIVE`
- `N8N_BASIC_AUTH_USER`
- `N8N_BASIC_AUTH_PASSWORD`
- `N8N_ENCRYPTION_KEY`

Use strong, unique values for passwords and the encryption key. Keep `.env` local and never commit it.

## Run with Docker

From the project root, start the services:

```sh
docker compose up -d
```

Check service status:

```sh
docker compose ps
```

Follow service logs:

```sh
docker compose logs -f
```

Stop the services:

```sh
docker compose down
```

The Compose configuration maps PostgreSQL to port `5432` and n8n to port `5678`. It uses a named Docker volume, `postgres_data`, for PostgreSQL data.

## n8n

n8n runs through the existing Docker Compose configuration. Once the services are running, open [http://localhost:5678](http://localhost:5678/) and sign in using the basic-auth username and password configured in `.env`.

To load a workflow, use n8n's workflow import option and select a JSON file from `workflows/`. Configure or select the required PostgreSQL and Ollama credentials in n8n after importing; the exports contain credential references, not the credential secrets themselves.

## Database

The Compose setup runs PostgreSQL 16 and configures n8n to connect to that database using the variables in `.env`. PostgreSQL data is stored in the `postgres_data` named volume. The `sql/` directory currently has no standalone SQL scripts; the database setup automation is in `workflows/database-setup.json`.

## Workflow Setup

The repository includes three n8n workflow exports:

- **Database Setup** - starts manually and runs a PostgreSQL node.
- **Lead Intelligence** - includes PostgreSQL nodes, an HTTP Request node, and an Ollama Chat Model node.
- **Upload leads** - accepts a form submission, extracts a file, and inserts rows using PostgreSQL.

Import the JSON files into n8n and configure the credentials and any node-specific settings required by your environment before running them.

## Security

- Never commit `.env`.
- Never commit API keys, passwords, tokens, or other credentials.
- Keep secrets in environment variables or n8n credential management, not in workflow exports.
- The repository ignores local backups and runtime data.

## Useful Commands

```sh
docker compose up -d
docker compose ps
docker compose logs -f
docker compose down
```
