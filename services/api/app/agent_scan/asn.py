"""IP -> ASN resolution over the IPinfo Lite `.mmdb`.

A lazy, fail-soft, module-level reader. IPinfo Lite ships a custom MaxMind-format
layout whose records are read with `maxminddb` (NOT geoip2's typed readers, which
expect the GeoLite2 record shape) - `reader.get(ip)` returns a plain dict with
`asn` / `as_name` / `country_code`. The `.mmdb` is baked into the API image;
when it is absent (dev/test/CI) resolution degrades to all-`None` -
telemetry then records a baseline-without-geo row, never an error.

Redact-then-derive (privacy.md): the caller passes the REDACTED `/24`-or-`/48`
network base, never a raw IP - the ASN of the network base equals the ASN of any
host in it, so geo precision is unchanged while no raw IP is ever read here.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict, cast

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AsnRecord(TypedDict):
    asn: str | None
    as_org: str | None
    country: str | None


_EMPTY: AsnRecord = {"asn": None, "as_org": None, "country": None}

_reader: Any | None = None
_loaded = False


def _get_reader() -> Any | None:
    """Open the `.mmdb` once (cached). Returns None when the file is absent/unreadable."""
    global _reader, _loaded
    if _loaded:
        return _reader
    _loaded = True
    path = get_settings().ipinfo_lite_db_path
    try:
        import maxminddb

        _reader = cast("Any", maxminddb).open_database(path)
    except Exception:  # fail-soft: absent/unreadable .mmdb -> geo degrades to None
        logger.info("agent_scan.asn_db_unavailable path=%s", path)
        _reader = None
    return _reader


def resolve(ip: str | None) -> AsnRecord:
    """Resolve `{asn, as_org, country}` for `ip` (already a redacted network base).

    All-`None` when no DB is loaded or the lookup misses - never raises."""
    reader: Any = _get_reader()
    if reader is None or not ip:
        return dict(_EMPTY)  # type: ignore[return-value]
    try:
        record = reader.get(ip)
    except Exception:  # a malformed lookup must never break the scan
        return dict(_EMPTY)  # type: ignore[return-value]
    if not isinstance(record, dict):
        return dict(_EMPTY)  # type: ignore[return-value]
    record_d = cast("dict[str, Any]", record)
    return {
        "asn": record_d.get("asn"),
        "as_org": record_d.get("as_name") or record_d.get("as_domain"),
        "country": record_d.get("country_code") or record_d.get("country"),
    }
