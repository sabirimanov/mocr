from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="METER_OCR_")

    host: str = "0.0.0.0"
    port: int = 8080
    download_timeout_seconds: float = 30.0
    max_image_bytes: int = 15 * 1024 * 1024
    ocr_use_angle_cls: bool = True
    regions_path: Path = Path("data/regions.yaml")
    # Comma-separated directories local image_path values must fall under.
    allowed_image_dirs: str = "data/images,/www/wwwroot/meter-ocr/data/images"


settings = Settings()
