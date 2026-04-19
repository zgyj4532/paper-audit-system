from pathlib import Path
from dotenv import load_dotenv
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into environment first
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # JWT
    JWT_SECRET_KEY: SecretStr | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    ENABLE_UUID_AUTH: int = 0

    # 应用级配置
    RUST_HTTP_PORT: int = 8193
    PYTHON_UVICORN_PORT: int = 8000
    DRAFT_EXPIRE_DAYS: int = 7
    MAX_FILE_SIZE_MB: int = 10
    qrcode_expire_seconds: int = 300

    HOST: str = ""

    # 数据库（可选，留空表示未配置）
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str | None = None
    MYSQL_PASSWORD: str | None = None
    MYSQL_DATABASE: str | None = None

    # 微信/支付相关
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""
    WECHAT_WXA_ENV_VERSION: str = "release"
    WECHAT_WXA_MSG_TOKEN: str = ""

    # 项目特有
    QWEN_API_KEY: str | None = None
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1"
    QWEN_MODEL: str = "qwen-max-latest"

    PYTHON_UPLOAD_DIR: Path = Path("./uploads")
    PYTHON_OUTPUT_DIR: Path = Path("./outputs")
    PYTHON_REPORT_DIR: Path = Path("./data/reports")
    PYTHON_TEMP_DIR: Path = Path("./data/temp")
    ARCHIVE_DIR: Path = Path("./data/archives")
    SQLITE_DB_PATH: Path = Path("./data/tasks.db")
    CHROMA_PERSIST_DIR: Path = Path("./data/chroma_db")
    CHROMA_COLLECTION_NAME: str = "academic_papers"
    CUSTOM_FONT_DIR: Path | None = None
    MAX_UPLOAD_SIZE: int = 50
    MAX_CONCURRENT_TASKS: int = 3
    UPLOAD_RETENTION_DAYS: int = 7
    REPORT_RETENTION_DAYS: int = 30
    REFERENCE_VERIFIER_BACKEND: str = "auto"  # auto|local|qwen
    LOCAL_REFERENCE_VERIFIER_MIN_RAM_MB: int = 3072
    LOCAL_REFERENCE_VERIFIER_ESTIMATED_RAM_MB: int = 768

    # LLM / processing
    LLM_CHUNK_SIZE: int = 800
    LLM_CHUNK_OVERLAP: int = 100
    LLM_QWEN_BATCH_SIZE: int = 4  # 并发 worker 数
    LLM_RATE_LIMIT: float = 0.5
    DEFAULT_ENABLED_MODULES: str = "typo,format,logic,reference"
    DEFAULT_STRICTNESS: int = 3


settings = Settings()
