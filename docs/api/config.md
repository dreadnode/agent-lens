# Config

Configuration models for experiment runs. All models use Pydantic for validation.

::: harness.config
    options:
      members:
        - SessionMode
        - SessionConfig
        - AgentConfig
        - RunConfig
        - load_config
        - build_provider_env
