"""Production ORM model registry — `Base.metadata` sees only these imports.

The eight **schema-backed** models — CatalogItem, Scan, Finding, ScanRun,
VendorVerification, VendorResponse (the original six) plus IngestionEvent and
MergeCandidate (I-04) — are GENERATED from `schemas/*.schema.json` via the codegen
pipeline (`app/models/generated/`, native PG enum columns). The ten **internal**
models — ItemSource, RateLimit, UploadFile, ArtifactBlob, ScanEvent, Author,
CrawlerCursor, PopularityFormula, AccessLog, AdminAuditLog — have no JSON-Schema
source and no wire DTO (never serialized over the API), so they stay hand-written
under `app/models/*.py`. (A table that IS serialized over the API must be
schema-driven/generated — see `.claude/rules/database.md` + `schema-driven-development.md`.)
Both sets share the one `Base` (`app/models/base.py`), re-exported by the generated
`_base.py`.

`app.models._relationships` attaches every cross-model `relationship()` (the
generator emits FK columns only). Importing this module registers all tables on
`Base.metadata`.
"""

# Side-effect import — attaches every cross-model relationship() (the generator
# emits FK columns only). It imports its own mapped-class dependencies, so import
# order here is irrelevant. The redundant `as` alias marks the intentional
# side-effect/re-export so linters don't flag it as unused.
from app.models import _relationships as _relationships
from app.models.access_log import AccessLog
from app.models.admin_audit_log import AdminAuditLog
from app.models.artifact_blob import ArtifactBlob
from app.models.author import Author
from app.models.base import Base
from app.models.crawler_cursor import CrawlerCursor
from app.models.generated import (
    CatalogItem,
    Finding,
    IngestionEvent,
    MergeCandidate,
    Scan,
    ScanRun,
    VendorResponse,
    VendorVerification,
)
from app.models.item_source import ItemSource
from app.models.popularity_formula import PopularityFormula
from app.models.rate_limit import RateLimit
from app.models.scan_event import ScanEvent
from app.models.upload_file import UploadFile

__all__ = [
    "AccessLog",
    "AdminAuditLog",
    "ArtifactBlob",
    "Author",
    "Base",
    "CatalogItem",
    "CrawlerCursor",
    "Finding",
    "IngestionEvent",
    "ItemSource",
    "MergeCandidate",
    "PopularityFormula",
    "RateLimit",
    "Scan",
    "ScanEvent",
    "ScanRun",
    "UploadFile",
    "VendorResponse",
    "VendorVerification",
]
