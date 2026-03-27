from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    tavily_api_key: str = ""
    host: str = "localhost"
    port: int = 10000
    search_country: str = "united states"
    max_search_results: int = 5
    max_scrape_urls: int = 5
    max_context_chars: int = 50_000
    report_format: str = "markdown"
    a2a_hmac_secret: str = ""
    actguard_api_key: str = ""
    actguard_gateway_url: str = "https://api.actguard.ai"

    # Model override for report generation (None = use openai_model)
    model_write_report: str | None = None

    # Embedding / chunk settings
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 1000
    chunk_overlap: int = 100
    similarity_threshold: float = 0.65


settings = Settings()
