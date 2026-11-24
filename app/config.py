import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if present
load_dotenv(BASE_DIR / ".env")


class Settings:
    PROJECT_NAME: str = "TenantShield"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Autonomous Security Deposit & Lease Rights Defender"
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Paths
    BASE_DIR: Path = BASE_DIR
    APP_DIR: Path = BASE_DIR / "app"
    STATIC_DIR: Path = APP_DIR / "static"
    TEMPLATES_DIR: Path = APP_DIR / "templates"
    MCP_SERVERS_DIR: Path = BASE_DIR / "mcp_servers"
    TEST_DATA_DIR: Path = BASE_DIR / "test_data"


settings = Settings()
