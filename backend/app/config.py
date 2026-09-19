from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    api_football_key: str = ""
    odds_api_key: str = ""
    environment: str = "development"


settings = Settings()
