# Khaira

[![Version](https://img.shields.io/badge/khaira-v0.2.4-blue)](https://pypi.org/project/khaira/)
[![License](https://img.shields.io/badge/License-MIT-green)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)

**Automated FastAPI scaffolding CLI and framework runtime.** Generate clean, production-grade 5-layer backend pipelines from simple model definitions, schemas, and CLI commands.

> **Package name:** `khaira` · **Primary command:** `khaira` (alias: `kaira`)

---

## Features

- **5-Layer Pipeline** — Model → Repository → Schema → Service → Router, with strict separation of concerns
- **Library Abstraction Layer** — First-class imports (`from khaira.http import Router, Depends`, `from khaira.models import Model`, `from khaira.schemas import Schema`, `from khaira.auth import OAuth2PasswordBearer`)
- **50+ Commands** — `generate`, `migrate`, `seed`, `deploy`, `monitor`, `cloud`, and more
- **Command Shortcuts** — `g` for `generate model`, `mr` for `migrate run`, and more
- **Shell Tab-Completion** — bash, zsh, fish, and PowerShell via `khaira --install-completion`
- **Monitoring** — Metrics, probes, mini dashboard, and alerts
- **Multi-DB Support** — PostgreSQL, MySQL, MongoDB (Beanie), SQLite
- **Docker** — Full container scaffolding with dynamic registry rendering
- **CI/CD** — GitHub, GitLab, Bitbucket pipeline generation
- **AI/Agents** — Built-in support for AI coding assistants and scaffolded project guidelines

---

## Quick Start

```bash
# Install
pip install khaira

# Scaffold a new project
khaira init myproject --db postgresql --auth jwt --docker

# Generate a model
khaira generate model User --fields "username:str, email:str, age:int"

# Create and run migrations
khaira migrate init
khaira migrate make "initial migration"
khaira migrate run

# Seed the database
khaira seed run

# Run the server
khaira run
```

---

## Installation

### From PyPI

```bash
pip install khaira
```

### From source

```bash
git clone https://github.com/hizWindy/DevFlow.git
cd DevFlow
pip install -e ".[all]"
```

---

## Command Reference

### Project

```
khaira init              Scaffold a new project
khaira upgrade           Upgrade project tier or features
khaira microservice      Split a monolith into microservices
khaira add-dep           Add a dependency
```

### Generation

```
khaira generate          Scaffold backend layers
khaira add               Add model relationships
khaira sync              Cascade field changes across all layers
```

### Database

```
khaira migrate           Alembic migration commands
khaira db                Database connection, status, and management
khaira seed              Database seeding
khaira migrate-docs      NoSQL document migration
```

### Operations

```
khaira run               Start the FastAPI server
khaira test              Test scaffold and run
khaira deploy            Deployment config generation
khaira docker            Docker configuration
khaira ci                CI/CD pipeline generation
khaira quality           Code quality tools
khaira cache             Redis cache management
khaira task              Celery background tasks
```

### Monitoring & Observability

```
khaira monitor           Runtime monitoring (metrics, probes, dashboard)
khaira status            Live project status snapshot
khaira profile           Route profiling
khaira loadtest          Load testing
khaira health-endpoint   Generate /health endpoint
```

### Integrations

```
khaira integrate         Third-party service integrations
khaira auth              Authentication scaffolding
khaira cloud             Cloud database providers
khaira ai                AI, RAG pipelines, and multi-agent scaffolding
```

### Utilities

```
khaira commands          Index of all available commands
khaira guide             Interactive guides
khaira recap             Command history viewer
khaira menu              Interactive command palette
khaira flags             Feature flag management
khaira export            Export data (xlsx/pdf/docx)
khaira events            Lifespan event scaffolding
khaira notifications     Notification service scaffolding
khaira audit             API auditing and security
khaira env               Environment management
khaira config            Project configuration
khaira docs              Documentation generation
```

---

## Architecture

Generated projects follow a strict 5-layer pipeline:

| Layer | Directory | Responsibility |
|---|---|---|
| **Model** | `models/` | SQLAlchemy ORM / Beanie ODM classes |
| **Repository** | `repositories/` | Database access, queries, commits |
| **Schema** | `schemas/` | Pydantic v2 DTOs (Base, Create, Update, Response) |
| **Service** | `services/` | Business logic, domain validation |
| **Router** | `routers/` | FastAPI path operations, dependency injection |

---

## Shortcuts

| Shortcut | Command |
|---|---|
| `g` | `generate model` |
| `gb` | `generate bulk` |
| `sm` | `sync model` |
| `mm` | `migrate make` |
| `mr` | `migrate run` |
| `st` | `status` |
| `up` | `docker up` |
| `dn` | `docker down` |
| `ds` | `docker status` |
| `q` | `quality` |
| `t` | `test run` |
| `?` | `menu` |

> Destructive commands (`db reset`, `migrate rollback`, `seed clear`) **never** have shortcuts.

---

## Contributing

See [AGENTS.md](AGENTS.md) for engine development guidelines.

```bash
# Run tests
pytest

# Lint
ruff check . && ruff format .

# Type check
mypy kaira
```

---

## License

MIT — see [LICENSE](LICENSE) for details.
