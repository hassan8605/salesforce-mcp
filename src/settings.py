from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # ─── Application ───────────────────────────────────────────
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    ENVIRONMENT: str = "development"

    # ─── Salesforce OAuth (Connected App) ──────────────────────
    SF_LOGIN_URL: str = "https://login.salesforce.com"
    SF_CLIENT_ID: str = ""        # Consumer Key from Connected App
    SF_CLIENT_SECRET: str = ""    # Consumer Secret from Connected App
    SF_REDIRECT_URI: str = "http://localhost:8000/api/auth/callback"

    # ─── Token Storage ─────────────────────────────────────────
    SF_TOKENS_DIR: str = "./tokens"   # override to /app/tokens in Docker

    # ─── Anthropic (NLP query endpoint) ────────────────────────
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
