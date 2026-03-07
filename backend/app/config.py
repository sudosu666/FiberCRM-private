from pydantic import BaseSettings, PostgreSQLDsn

class Settings(BaseSettings):
    app_name: str = 'FiberOps CRM'
    database_url: PostgreSQLDsn = 'postgresql+asyncpg://fiber:password@localhost:5432/fibercrm'
    jwt_secret: str = 'super-secret-key'
    jwt_algorithm: str = 'HS256'
    access_token_expire_minutes: int = 60

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

settings = Settings()
