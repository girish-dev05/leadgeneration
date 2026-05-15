from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = Field(default='Lead Engine', alias='APP_NAME')
    app_host: str = Field(default='127.0.0.1', alias='APP_HOST')
    app_port: int = Field(default=8000, alias='APP_PORT')

    mysql_host: str = Field(default='127.0.0.1', alias='MYSQL_HOST')
    mysql_port: int = Field(default=3306, alias='MYSQL_PORT')
    mysql_user: str = Field(default='root', alias='MYSQL_USER')
    mysql_password: str = Field(default='', alias='MYSQL_PASSWORD')
    mysql_db: str = Field(default='lead_engine', alias='MYSQL_DB')
    database_url: str = Field(default='', alias='DATABASE_URL')

    default_region: str = Field(default='IN', alias='DEFAULT_REGION')

    smtp_host: str = Field(default='smtp.gmail.com', alias='SMTP_HOST')
    smtp_port: int = Field(default=587, alias='SMTP_PORT')
    smtp_user: str = Field(default='', alias='SMTP_USER')
    smtp_password: str = Field(default='', alias='SMTP_PASSWORD')
    smtp_from: str = Field(default='', alias='SMTP_FROM')

    outreach_enabled: bool = Field(default=False, alias='OUTREACH_ENABLED')
    outreach_batch_size: int = Field(default=10, alias='OUTREACH_BATCH_SIZE')

    call_agent_webhook: str = Field(default='', alias='CALL_AGENT_WEBHOOK')
    call_agent_token: str = Field(default='', alias='CALL_AGENT_TOKEN')
    openai_api_key: str = Field(default='', alias='OPENAI_API_KEY')

    @property
    def db_url(self) -> str:
        if self.database_url:
            url = self.database_url.strip()
            if url.startswith('postgres://'):
                return 'postgresql+psycopg://' + url[len('postgres://'):]
            if url.startswith('postgresql://'):
                return 'postgresql+psycopg://' + url[len('postgresql://'):]
            return url
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}@"
            f"{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )

    @property
    def is_postgres(self) -> bool:
        return self.db_url.startswith('postgresql')


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
