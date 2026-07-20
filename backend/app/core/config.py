"""Application configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


# 项目 backend/ 目录，用于本地开发默认路径
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_DEFAULT_UPLOAD_DIR = str(_BACKEND_DIR / "uploads")


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Skdy Ticket System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://skdy:skdy123@localhost:5433/skdy_ticket"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Ticket
    TICKET_NUMBER_PREFIX: str = "TKT"

    # Logging
    LOG_LEVEL: str = "INFO"

    # SLA
    SLA_WARNING_RATIO: float = 0.2  # 剩余时间 ≤20% 时预警
    SLA_FIRST_RESPONSE_WARNING_MINUTES: int = 30  # 首次响应剩余30分钟发钉钉
    SLA_SOLUTION_WARNING_MINUTES: int = 60  # 解决剩余60分钟发钉钉

    # DingTalk
    DINGTALK_APP_KEY: str = ""
    DINGTALK_APP_SECRET: str = ""
    DINGTALK_AGENT_ID: str = ""  # 工作通知 agentId

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Uploads / Attachments
    # 本地开发默认写到 backend/uploads；Docker 中通过 .env 覆盖为 /app/uploads
    UPLOAD_DIR: str = _DEFAULT_UPLOAD_DIR
    PUBLIC_UPLOAD_URL: str = "/uploads"
    UPLOAD_MAX_SIZE: int = 10 * 1024 * 1024  # 10 MB

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
