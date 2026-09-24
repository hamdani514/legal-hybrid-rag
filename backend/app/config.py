from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGO_URL: str = "mongodb://localhost:27017"
    REDIS_URL: str = ""
    DB_NAME: str = "legal_rag"
    OPENAI_API_KEY: str = ""
    
    # Gemini API Settings (Primary)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    
    # Groq Cloud API Settings (Preserved/Commented in active provider)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # Retrieval: where the ingestion pipeline writes its node->vector index.
    # Empty means "use backend/app/connection". Accepts a directory of
    # *_mappings.json files or a single JSON file.
    JSON_INDEX_PATH: str = ""

    # Retrieval: token budget for the context handed to the LLM.
    MAX_CONTEXT_TOKENS: int = 8000

    # Parser Configuration
    USE_LLM_PARSER: bool = True
    PARSER_MODE: str = "hybrid"  # Options: "hybrid", "pure_llm", "rule_based"

    # LLM Provider: "gemini", "groq", or "ollama"
    LLM_PROVIDER: str = "gemini"

    # Ollama Local Settings (Fallback)
    OLLAMA_MODEL: str = "mistral"
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"

    # SMTP & Email Settings
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    REACTIVATION_TOKEN_EXPIRY_DAYS: int = 30

    # Auth & Security
    JWT_SECRET: str = "long_random_string_here"
    GOOGLE_CLIENT_ID: str = ""
    RECAPTCHA_SECRET_KEY: str = ""
    RECAPTCHA_SCORE_THRESHOLD: float = 0.5
    CONTACT_RECEIVER_EMAIL: str = "verdictaisupport@gmail.com"

    # Google Drive Integration
    GOOGLE_DRIVE_TARGET_EMAIL: str = "verdictaisupport@gmail.com"
    GOOGLE_DRIVE_FOLDER_ID: str = ""
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "service_account.json"
    GOOGLE_DRIVE_TOKEN_FILE: str = "token.json"
    GOOGLE_DRIVE_CLIENT_SECRET_FILE: str = "client_secret.json"
    GOOGLE_DRIVE_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=[
            str(Path(__file__).resolve().parents[1] / ".env"),  # backend/.env
            str(Path(__file__).resolve().parents[2] / ".env"),  # repo-root .env (fallback)
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
