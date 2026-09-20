# Kaira

[![Version](https://img.shields.io/badge/khaira-v0.2.3-blue)](https://pypi.org/project/khaira/)
[![License](https://img.shields.io/badge/License-MIT-green)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)

**Automated FastAPI scaffolding CLI.** Generate clean, production-grade 5-layer backend pipelines from simple model definitions.

> **Also known as:** DevFlow (former name)  
> **Package name:** `khaira` · **CLI command:** `kaira` or `khaira`

---

## Features

- **5-Layer Pipeline** — Model → Repository → Schema → Service → Router, with strict separation of concerns
- **50+ Commands** — `generate`, `migrate`, `seed`, `deploy`, `monitor`, `cloud`, and more
- **Command Shortcuts** — `g` for `generate model`, `mr` for `migrate run`, and more
- **Shell Tab-Completion** — bash, zsh, fish, and PowerShell via `kaira --install-completion`
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
kaira init myproject --db postgresql --auth jwt --docker

# Generate a model
kaira generate model User --fields "username:str, email:str, age:int"

# Create and run migrations
kaira migrate init
kaira migrate make "initial migration"
kaira migrate run

# Seed the database
kaira seed run

# Run the server
kaira run
```

---

## Installation

### From PyPI

```bash
pip install khaira
```

### From source

```bash
git clone https://github.com/hizWindy/kaira.git
cd kaira
pip install -e ".[all]"
```

---

## Command Reference

### Project

```
kaira init              Scaffold a new project
kaira upgrade           Upgrade project tier or features
kaira microservice      Split a monolith into microservices
kaira add-dep           Add a dependency
```

### Generation

```
kaira generate          Scaffold backend layers
kaira add               Add model relationships
kaira sync              Cascade field changes across all layers
```

### Database

```
kaira migrate           Alembic migration commands
kaira db                Database connection, status, and management
kaira seed              Database seeding
kaira migrate-docs      NoSQL document migration
```

### Operations

```
kaira run               Start the FastAPI server
kaira test              Test scaffold and run
kaira deploy            Deployment config generation
kaira docker            Docker configuration
kaira ci                CI/CD pipeline generation
kaira quality           Code quality tools
kaira cache             Redis cache management
kaira task              Celery background tasks
```

### Monitoring & Observability

```
kaira monitor           Runtime monitoring (metrics, probes, dashboard)
kaira status            Live project status snapshot
kaira profile           Route profiling
kaira loadtest          Load testing
kaira health-endpoint   Generate /health endpoint
```

### Integrations

```
kaira integrate         Third-party service integrations
kaira auth              Authentication scaffolding
kaira cloud             Cloud database providers
kaira ai                AI, RAG pipelines, and multi-agent scaffolding
```

### Utilities

```
kaira commands          Index of all available commands
kaira guide             Interactive guides
kaira recap             Command history viewer
kaira menu              Interactive command palette
kaira flags             Feature flag management
kaira export            Export data (xlsx/pdf/docx)
kaira events            Lifespan event scaffolding
kaira notifications     Notification service scaffolding
kaira audit             API auditing and security
kaira env               Environment management
kaira config            Project configuration
kaira docs              Documentation generation
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
