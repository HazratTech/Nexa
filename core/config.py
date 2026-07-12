from loguru import logger
from pydantic_settings import BaseSettings
from dotenv import  load_dotenv

load_dotenv()

from typing import Optional

class Settings(BaseSettings):
    discord_token: str
    pixabay_api: str
    mongo_connection: str
    database_name: str
    perspective_api_key: str
    sightengine_api_user: str
    sightengine_api_secret: str
    openai_api_key: str
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if not self.redis_url:
            self.redis_url = f"redis://{self.redis_host}:{self.redis_port}/0"

    class Config:
        env_file = ".env"
        case_sensitive = False

try:
    settings = Settings()
except Exception as e:
    logger.error(f"Failed to load settings: {e}")









