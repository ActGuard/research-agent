from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    tavily_api_key: str = ""
    host: str = "localhost"
    port: int = 10000
    max_sub_queries: int = 4
    max_search_results: int = 5
    report_format: str = "markdown"
    max_research_rounds: int = 2
    max_sub_queries_quick: int = 1
    max_sub_queries_standard: int = 4
    max_sub_queries_deep: int = 6
    max_evidence_per_source: int = 5
    a2a_hmac_secret: str = ""
    actguard_api_key: str = ""
    actguard_gateway_url: str = "https://api.actguard.ai"

    max_worker_iterations: int = 2

    # Supervisor / researcher settings
    max_supervisor_iterations: int = 3
    max_researcher_tool_calls: int = 10
    max_concurrent_researchers: int = 3

    # Per-step model overrides (None = use openai_model default)
    model_classify: str | None = None
    model_brief: str | None = None
    model_supervisor: str | None = None
    model_researcher: str | None = None
    model_compress: str | None = None
    model_write_report: str | None = None
    model_refine_report: str | None = None


settings = Settings()
