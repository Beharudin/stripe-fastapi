from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str 

    JWT_SECRET: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None

    model_config = {
        "env_file": ".env",
        # Allow extra unrelated env vars (e.g. mail settings) to avoid startup failure
        "extra": "allow",
    }


settings = Settings()