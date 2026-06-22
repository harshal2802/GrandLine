# Project: TaskFlow API

## What we're building

A REST API for a task management application that supports creating, assigning, filtering, and tracking tasks across teams. The API serves a React frontend (built by a separate team) and a future mobile app.

## Who it's for

Small-to-medium engineering teams (5-30 people) who need a lightweight alternative to Jira. Primary users interact through the frontend; this API is the backend contract.

## Tech stack

- Language: TypeScript (Node.js 20)
- Framework: Express 4.x
- Database: PostgreSQL 16
- ORM: Prisma 5.x
- Auth: JWT (access + refresh tokens)
- Validation: Zod
- Testing: Vitest + Supertest
- Deployment: Docker containers on AWS ECS

## API design

- Style: REST with JSON request/response bodies
- Versioning strategy: URL prefix `/api/v1/`
- Auth method: Bearer token (JWT), refresh via `/api/v1/auth/refresh`
- API spec location: `docs/openapi.yaml`

## Data layer

- Primary database: PostgreSQL 16 (AWS RDS)
- ORM: Prisma 5.x
- Migration tool: Prisma Migrate
- Caching layer: Redis for session data and rate limiting

## Infrastructure

- Deployment: Docker containers on ECS behind an ALB
- Queue / async: BullMQ (Redis-backed) for email notifications and webhook delivery
- Secrets management: AWS Secrets Manager, loaded at container start

## What good output looks like

- Follows the service/repository pattern already in the codebase
- Includes input validation at the controller layer using Zod
- Returns consistent error shapes
- Includes unit tests for the service layer and integration tests for the endpoint
- TypeScript strict mode compatible, no `any` types

## Constraints (what the AI should never do or suggest)

- Never use raw SQL queries; always use Prisma
- Never put business logic in route handlers or Prisma queries in controllers
- Never disable TypeScript strict mode or use `any`
- Never store secrets in code or config files
- Never return stack traces or internal error details in API responses

## Current state

Core infrastructure is in place: project scaffolding, auth endpoints (register, login, refresh), and the user CRUD. We are now building the task management domain (tasks, labels, comments).
