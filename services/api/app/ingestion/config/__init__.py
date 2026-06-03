"""YAML-driven provider configuration for the ingestion pipeline.

Each provider is declared in `sources/<name>.yaml` and validated into a
`SourceConfig`. The generic framework consumes the config; a provider's Python
adapter supplies only the bespoke `list_items()` / `normalize()` logic it can't
express declaratively. Adding a new provider = a YAML file (+ optional small
normalizer), never a new framework class. See `loader.py`.
"""

from app.ingestion.config.loader import (
    SourceConfig,
    get_source_config,
    load_source_configs,
)

__all__ = ["SourceConfig", "get_source_config", "load_source_configs"]
