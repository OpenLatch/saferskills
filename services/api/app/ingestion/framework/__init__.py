"""Ingestion adapter framework — config-driven (YAML) provider pipeline.

Every adapter inherits a framework superclass (RegistryAdapter / WebhookAdapter /
ScrapingAdapter) and is parameterised by a `SourceConfig` loaded from
`app/ingestion/config/sources/<name>.yaml`. The framework supplies the HTTP
client (HTTPX + Hishel + per-source rate limit + SSRF allowlist), the OutboxWriter,
the MergeEngine (GitHub-wins dedup + fuzzy queue), the content-hash util, and the
classifier (kind / quality_tier / agent_compatibility). See .claude/rules/ingestion.md.
"""
