from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "GrandLine API"
    app_version: str = "0.1.0"
    debug: bool = False

    # PostgreSQL
    database_url: str = "postgresql+psycopg://grandline:grandline@localhost:5432/grandline"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 10080  # 7 days

    # LLM Providers (Dial System)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Default provider/model for newly charted voyages (every crew role).
    # Editable per voyage afterwards via PUT /voyages/{id}/dial-config.
    dial_default_provider: str = "anthropic"
    dial_default_model: str = "claude-sonnet-4-20250514"

    # Claude Code CLI provider (provider name: "claude_code").
    # Auth comes from the CLI itself (claude login / CLAUDE_CODE_OAUTH_TOKEN /
    # ANTHROPIC_API_KEY in the process environment) — no key stored here.
    claude_code_cli_path: str = "claude"
    claude_code_timeout_seconds: int = 300
    claude_code_max_turns: int = 1
    claude_code_workspace: str = ""  # cwd for the CLI; empty = system temp dir
    claude_code_extra_args: str = ""  # extra CLI flags, shlex-split
    # Per-user Claude Code (Phase C0): the command ClaudeAuthService runs INSIDE the
    # user's Cabin to begin the device-login / token-capture flow. The CLI prints a
    # verification URL the user approves out-of-band; the captured
    # CLAUDE_CODE_OAUTH_TOKEN is then vaulted in the Sea Chest (kind="claude_code")
    # and the adapter runs as the user. Configurable so deployments can pin the exact
    # `claude setup-token`-style invocation. Env `GRANDLINE_CLAUDE_CODE_LOGIN_COMMAND`.
    claude_code_login_command: str = "claude setup-token"

    # Vivre Card (State Checkpointing)
    vivre_card_checkpoint_interval_seconds: int = 300  # 5 minutes
    vivre_card_cleanup_keep_last_n: int = 10

    # Execution Service (Sandbox)
    execution_backend: str = "gvisor"
    execution_image: str = "python:3.13-slim"
    execution_memory_limit: str = "256m"
    execution_cpu_quota: int = 50000
    execution_cpu_period: int = 100000
    execution_default_timeout: int = 30
    execution_network_enabled: bool = False
    execution_gvisor_runtime: str = "runsc"

    # Bedside Browser (Phase 23): the Doctor's browser-in-the-loop verification
    # backend. "null" (default) is deterministic and browser-free (CI-safe);
    # "playwright" opts into a real headless browser (Playwright is an optional,
    # opt-in dependency — NOT in requirements.txt). Env: GRANDLINE_BROWSER_BACKEND.
    browser_backend: str = "null"

    # Git Integration
    git_sandbox_image: str = "bitnami/git:latest"
    git_sandbox_memory_limit: str = "512m"
    git_default_branch: str = "main"
    git_author_name: str = "GrandLine Crew"
    git_author_email: str = "crew@grandline.dev"
    github_api_token: str = ""
    # Return Bottle (Phase 22): the fixed GitHub API host the completion-time
    # write-back contacts. ALWAYS this host — never one derived from a voyage's
    # untrusted `origin` payload. Env only; reuses `github_api_token` for auth.
    github_api_base_url: str = "https://api.github.com"
    # Per-user GitHub (Phase A3): the GitHub OAuth App client_id used for the
    # device-code flow that lets each user connect THEIR OWN GitHub account. The
    # token lands in the Sea Chest (kind="github"); git ops then run with the
    # user's token + identity when connected, else the env `github_api_token`.
    # Env only (`GRANDLINE_GITHUB_OAUTH_CLIENT_ID`) — never user-supplied. Unset ==
    # the device flow cannot start (clear error).
    github_oauth_client_id: str = ""

    # Message in a Bottle (Phase 21): external triggers via signed webhook.
    # The shared secret GitHub signs webhook deliveries with (X-Hub-Signature-256).
    # Unset == reject every delivery (we never accept an unverified payload). Env only.
    github_webhook_secret: str | None = None
    # A webhook carries no GrandLine identity; the owning user of a triggered voyage
    # is resolved from this configured email (operators choose the account).
    trigger_default_user_email: str | None = None
    # An inbound GitHub issue only charts a course when it carries this label.
    trigger_label: str = "grandline"

    # Sea Chest (Phase 0a): the encryption key for the per-user credential vault.
    # An arbitrary string is fine — it is deterministically derived into a Fernet
    # key. Env ``GRANDLINE_SEACHEST_KEY``. Unset + debug derives a STABLE dev key
    # (with a warning); unset + non-debug fails closed when encryption is needed.
    # NEVER stored in code or the DB — credentials are encrypted at rest with this.
    seachest_key: str | None = None

    # Cabin (Phase 0b): the per-user persistent sandbox container. The backend is
    # swappable (env GRANDLINE_CABIN_BACKEND): "null" (default) is deterministic and
    # container-free (CI-safe, the analogue of InProcessDeploymentBackend); "gvisor"
    # opts into a real persistent-per-user gVisor container (lazily imports aiodocker
    # — NOT needed for startup or tests).
    cabin_backend: str = "null"
    # Idle reaper + hard max lifetime: a Cabin is destroyed once idle past the idle
    # timeout OR older than the max lifetime, whichever comes first, so a Cabin never
    # outlives its need. The reaper loop runs every reap-interval seconds.
    cabin_idle_timeout_seconds: int = 1800  # 30 min idle
    cabin_max_lifetime_seconds: int = 3600  # 60 min hard cap
    cabin_reap_interval_seconds: int = 300  # reaper cadence
    # Deny-by-default egress allow-list for the Cabin (empty == no egress). Only the
    # hosts a materialized credential needs should be opened, e.g.
    # ["api.github.com", "github.com"] for the github token (A3 git ops) and the
    # Anthropic endpoint (e.g. "api.anthropic.com") for the claude_code token (C0).
    cabin_network_allow: list[str] = []

    # Demo mode (#56): a scripted voyage replayable via `make demo`, no API key.
    demo_mode: bool = False

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_prefix": "GRANDLINE_", "env_file": ".env"}


settings = Settings()
