from pathlib import Path
from dotenv import load_dotenv
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

    # 应用级配置
    RUST_HTTP_PORT: int = 8193
    RUST_LOG: str = "info"
    RUST_TEMP_DIR: Path = Path("./temp/rust_engine")

    ENGINE_JAVA_HTTP_PORT: int = 8081
    ENGINE_JAVA_GRPC_PORT: int = 9191
    ENGINE_JAVA_BASE_URL: str = "http://127.0.0.1:8081"
    ENGINE_JAVA_JAR_PATH: Path = Path(
        "./engine-java/target/engine-java-0.1.0-SNAPSHOT.jar"
    )
    ENGINE_JAVA_MAIN_CLASS: str = "com.auditor.engine.EngineApplication"
    ENGINE_JAVA_START_MODE: str = "jar"
    ENGINE_JAVA_TIMEOUT_SECONDS: int = 60

    PYTHON_UVICORN_PORT: int = 8000
    PYTHON_UPLOAD_DIR: Path = Path("./uploads")
    PYTHON_OUTPUT_DIR: Path = Path("./outputs")
    PYTHON_REPORT_DIR: Path = Path("./data/reports")
    PYTHON_TEMP_DIR: Path = Path("./data/temp")
    ARCHIVE_DIR: Path = Path("./data/archives")
    SQLITE_DB_PATH: Path = Path("./data/tasks.db")
    CHROMA_PERSIST_DIR: Path = Path("./data/chroma_db")
    CHROMA_COLLECTION_NAME: str = "academic_papers"

    HOST: str = ""

    # 数据库（可选，留空表示未配置）
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str | None = None
    MYSQL_PASSWORD: str | None = None
    MYSQL_DATABASE: str | None = None

    # 项目特有
    QWEN_API_KEY: str | None = None
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/api/v1"
    QWEN_MODEL: str = "qwen-max-latest"

    CUSTOM_FONT_DIR: Path | None = None
    MAX_UPLOAD_SIZE: int = 50
    MAX_FILE_SIZE_MB: int = 50
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
    RULE_AUDIT_BACKEND: str = "java_http"  # java_http|local|hybrid


settings = Settings()
