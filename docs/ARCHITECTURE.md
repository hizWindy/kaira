# Kaira ⚡ — Project Architecture & Deep Dive

> **In plain English:** Kaira is a tool that does the boring, repetitive setup work for you — so you can focus on building the actual product.
>
> **In developer terms:** Kaira is a Python-based CLI scaffolding tool that auto-generates a complete FastAPI 5-layer backend pipeline (model → repository → schema → service → router) from a single command using Jinja2 templates.

---

## 📌 Current Status

| | |
|---|---|
| **Name** | Kaira (formerly DevFlow) |
| **Version** | 0.1.0 |
| **CLI command** | `kaira` |
| **Python package** | `kaira` |
| **Project config file** | `.kaira.json` |
| **Command groups registered** | 43 |
| **Test suite** | 264 passed, 1 skipped |
| **Supported Python** | 3.10 → 3.14 (verified installs, wheels-only, no compiler needed) |
| **Default database** | SQLite (zero-config, boots on a fresh clone) |

**In short:** the tool is stable and fully working. The generated projects are now *self-contained* — anyone can clone one from GitHub and run it without having Kaira installed — and the dependency setup installs cleanly across Python 3.10–3.14.

---

## 🤔 What Problem Does It Solve?

### For everyone
Every time a developer builds a web application backend, they have to write the same types of files over and over again — files that handle data, files that talk to the database, files that validate input, and files that expose the API. This is tedious, slow, and error-prone.

**Kaira automates all of that.**

### For developers
Manually writing boilerplate for every new model (SQLAlchemy ORM, Pydantic schemas, FastAPI routers, service layer, repository pattern) is repetitive and inconsistent across team members. Kaira enforces a consistent 5-layer architecture and generates all layers from a single model definition.

---

## ⚡ What It Does — One Command, Five Files

```bash
kaira generate model User --fields "username:str, email:str, age:int"
```

It instantly creates **5 ready-to-use files**:

| What it creates | What it does |
|---|---|
| `models/user.py` | Defines what a User looks like in the database |
| `repositories/user_repository.py` | Handles saving, fetching, updating, and deleting users |
| `schemas/user_schema.py` | Validates data coming in and going out of the API |
| `services/user_service.py` | Contains the business rules and logic |
| `routers/user_router.py` | Exposes the API endpoints |

---

## 🗄️ Database Architecture

| Database | Technology used | Server needed? |
|---|---|---|
| SQLite (default) | Async SQLAlchemy + aiosqlite | No — file-based, zero-config |
| PostgreSQL | Async SQLAlchemy + asyncpg | Yes (or `docker compose up -d db`) |
| MySQL | Async SQLAlchemy + aiomysql | Yes (or Docker) |
| MongoDB | Motor + Beanie ODM | Yes (or Docker) |

---

## 🛠 Technology Stack

| Component | Library | Why |
|---|---|---|
| CLI framework | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) | Beautiful, typed CLI with rich terminal output |
| Templating engine | [Jinja2](https://jinja.palletsprojects.com/) | Flexible, powerful code generation |
| ORM | [SQLAlchemy 2.x](https://docs.sqlalchemy.org/en/20/) | Industry-standard Python database toolkit |
| Data validation | [Pydantic v2](https://docs.pydantic.dev/) | Fast, modern data validation |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) (`fastapi[standard]`) | High-performance async API framework + official CLI |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) | Database schema versioning |
| Logging | [Loguru](https://github.com/Delgan/loguru) | Simple, structured logging |
| Caching | [Redis](https://redis.io/) | In-memory key-value database for fast response caching |
| Background Jobs | [Celery](https://docs.celeryq.dev/) | Distributed task queue for asynchronous processing |
| Interactive Prompts | [InquirerPy](https://inquirerpy.readthedocs.io/) | Keyboard-driven interactive CLI prompts with custom styling |
