from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'Villas V2'
    app_env: str = 'development'
    public_url: str = 'http://127.0.0.1:8001'
    trusted_proxy: str = '127.0.0.1'
    cookie_secure: bool = False
    cookie_samesite: str = 'lax'
    session_cookie_name: str = 'villas_v2_session'
    session_ttl_minutes: int = 30
    login_rate_window_seconds: int = 300
    login_rate_ip_limit: int = 25
    login_rate_identifier_limit: int = 8
    login_rate_block_seconds: int = 900
    business_timezone: str = 'Europe/Lisbon'
    database_url: str = Field(..., repr=False)
    database_url_test: str = Field(..., repr=False)
    app_secret: str = Field(..., repr=False)
    session_secret: str = Field(..., repr=False)
    csrf_secret: str = Field(..., repr=False)
    log_level: str = 'INFO'
    media_root: Path = Path('media')
    log_dir: Path = Path('logs')
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = Field(default='', repr=False)
    smtp_from: str = ''
    trusted_proxies: str = '127.0.0.1'

    @field_validator(
        'app_env',
        'public_url',
        'trusted_proxy',
        'cookie_samesite',
        'session_cookie_name',
        'business_timezone',
        'database_url',
        'database_url_test',
        'app_secret',
        'session_secret',
        'csrf_secret',
        'log_level',
        'smtp_host',
        'smtp_user',
        'smtp_from',
        'trusted_proxies',
        mode='before',
    )
    @classmethod
    def _strip_string_values(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator('cookie_secure', mode='before')
    @classmethod
    def _parse_cookie_secure(cls, value):
        if isinstance(value, str):
            cleaned = value.strip().casefold()
            return cleaned in {'1', 'true', 'yes', 'on'}
        return value

    @property
    def trusted_proxy_values(self) -> str:
        values = [self.trusted_proxy, self.trusted_proxies]
        return ','.join(dict.fromkeys(value.strip() for value in values if value.strip()))

    @property
    def cookie_secure_flag(self) -> bool:
        if self.app_env.lower() in {'production', 'prod'}:
            return True
        return self.cookie_secure


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
