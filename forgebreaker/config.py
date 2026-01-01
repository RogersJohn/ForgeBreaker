from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "ForgeBreaker"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://localhost:5432/forgebreaker"

    mlforge_url: str = "https://backend-production-b2b8.up.railway.app"

    anthropic_api_key: str = ""

    # Feature flag for candidate pool filtering (PR 4)
    # When True, uses filtered candidate pool instead of full collection
    # Default: True (filtered pool enabled, explicit opt-out available)
    use_filtered_candidate_pool: bool = True

    # ==========================================================================
    # COST CONTROLS (PR 105)
    # This is a demo project. These limits protect against abuse and cost overruns.
    # ==========================================================================

    # Kill switch: Set to false to disable all LLM functionality
    llm_enabled: bool = True

    # Per-IP rate limit (requests per day)
    # Demo users get 20 requests per day per IP address
    requests_per_ip_per_day: int = 20

    # Global daily LLM budget (hard caps)
    # These limits apply across ALL users combined
    max_llm_calls_per_day: int = 500
    max_tokens_per_day: int = 500_000


settings = Settings()


# =============================================================================
# CANDIDATE POOL SAFETY LIMITS
# =============================================================================

# Minimum pool size - below this, fall back to full collection
# (pool too small to build meaningful deck)
MIN_CANDIDATE_POOL_SIZE = 10

# Maximum pool size - above this, fall back to full collection
# (pool not sufficiently filtered, no benefit)
MAX_CANDIDATE_POOL_SIZE = 100
