# Prompt: Database Models & Core Schemas
**File**: pdd/prompts/features/core/grandline-03-database-models.md
**Created**: 2026-04-05
**Project type**: Full-stack (FastAPI backend, PostgreSQL)
**Issue**: #4

## Context
GrandLine backend is scaffolded under `src/backend/` with async SQLAlchemy, Alembic, and psycopg. A `Base` declarative base and async session factory exist in `app/models/__init__.py`. Alembic is configured in `alembic/env.py` pointing at the same DB. PostgreSQL 16 runs via Docker Compose.

### One Piece domain model
- **Voyage**: A user-submitted task that flows through the pipeline
- **VoyagePlan**: Captain's decomposition of a voyage into phases
- **Poneglyph**: Navigator's PDD prompt artifacts for each phase
- **VivreCard**: Agent state checkpoints (JSONB) for failover
- **CrewAction**: Ship's Log entries — every agent action recorded
- **DialConfig**: Per-voyage LLM provider/model mapping for each crew role

### Conventions
- Database tables: snake_case, plural (`voyages`, `vivre_cards`)
- Classes: PascalCase (`Voyage`, `VivreCard`)
- JSONB for flexible data (agent state, crew config, plan phases)
- All schema changes via Alembic migrations
- Pydantic schemas for all request/response shapes

## Task
Create all SQLAlchemy models, the initial Alembic migration, Pydantic request/response schemas, and a seed data script for the GrandLine domain.

## Input
- Existing `Base` in `app/models/__init__.py`
- Existing Alembic setup in `alembic/`
- PostgreSQL 16 via Docker Compose

## Output format

### Models (`app/models/`)
```
app/models/
  __init__.py     — Base, engine, session (update to import all models)
  user.py         — User model
  voyage.py       — Voyage + VoyagePlan models
  poneglyph.py    — Poneglyph model
  vivre_card.py   — VivreCard model
  crew_action.py  — CrewAction model
  dial_config.py  — DialConfig model
```

### Schemas (`app/schemas/`)
```
app/schemas/
  __init__.py
  user.py         — UserCreate, UserRead
  voyage.py       — VoyageCreate, VoyageRead, VoyagePlanRead
  poneglyph.py    — PoneglyphRead
  vivre_card.py   — VivreCardRead, VivreCardCreate
  crew_action.py  — CrewActionRead
  dial_config.py  — DialConfigRead, DialConfigUpdate
```

### Migration
```
alembic/versions/001_initial_schema.py
```

### Seed script
```
scripts/seed.py  — Populates dev DB with sample data
```

## Model Definitions

### User
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK, default uuid4 |
| email | String(255) | unique, indexed |
| username | String(100) | unique, indexed |
| hashed_password | String(255) | |
| is_active | Boolean | default True |
| created_at | DateTime | server default now |
| updated_at | DateTime | on update now |

### Voyage
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id |
| title | String(255) | |
| description | Text | |
| status | String(50) | CHARTED, PLANNING, PDD, TDD, BUILDING, REVIEWING, DEPLOYING, COMPLETED, FAILED, PAUSED, CANCELLED |
| target_repo | String(500) | Git repo URL for agent work |
| created_at | DateTime | |
| updated_at | DateTime | |

### VoyagePlan
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| voyage_id | UUID | FK → voyages.id |
| phases | JSONB | Array of phase objects with name, description, assigned_to, depends_on |
| created_by | String(50) | "captain" |
| created_at | DateTime | |

### Poneglyph
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| voyage_id | UUID | FK → voyages.id |
| phase_number | Integer | Which phase this Poneglyph is for |
| content | Text | The PDD prompt content |
| metadata | JSONB | Architecture decisions, constraints, file paths |
| created_by | String(50) | "navigator" |
| created_at | DateTime | |

### VivreCard
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| voyage_id | UUID | FK → voyages.id |
| crew_member | String(50) | captain, navigator, doctor, shipwright, helmsman |
| state_data | JSONB | Serialized agent state |
| checkpoint_reason | String(100) | interval, failover, pause, migration |
| created_at | DateTime | |

### CrewAction
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| voyage_id | UUID | FK → voyages.id |
| crew_member | String(50) | Which agent |
| action_type | String(100) | e.g., plan_created, poneglyph_drafted, test_written, code_generated, deployed |
| summary | Text | Human-readable description |
| details | JSONB | Full action payload |
| created_at | DateTime | |

### DialConfig
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| voyage_id | UUID | FK → voyages.id, unique (one config per voyage) |
| role_mapping | JSONB | `{ "captain": { "provider": "anthropic", "model": "claude-sonnet", "temperature": 0.7 }, ... }` |
| fallback_chain | JSONB | `{ "captain": ["anthropic", "openai", "local"], ... }` |
| created_at | DateTime | |
| updated_at | DateTime | |

## Constraints
- All models use UUID primary keys (not auto-increment integers)
- Use `mapped_column` with type annotations (SQLAlchemy 2.0 style)
- JSONB columns use `sqlalchemy.dialects.postgresql.JSONB`
- Foreign keys indexed automatically
- `created_at` uses `server_default=func.now()`
- `updated_at` uses `onupdate=func.now()`
- Voyage status should be a Python enum used in both model and schema
- Pydantic schemas use `model_config = ConfigDict(from_attributes=True)` for ORM mode
- Tests: model instantiation, schema validation, enum coverage

## Acceptance Criteria
- [ ] All 7 models created with proper relationships and indexes
- [ ] Alembic migration applies cleanly to fresh PostgreSQL
- [ ] Pydantic schemas validate correctly (unit tests)
- [ ] VoyageStatus enum used consistently
- [ ] JSONB columns accept nested structures
- [ ] Seed script creates sample voyage with plan, poneglyphs, vivre cards, and crew actions
- [ ] `alembic downgrade base` reverses cleanly
