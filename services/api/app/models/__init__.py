"""Production ORM model registry — `Base.metadata` sees only these imports.

The six **schema-backed** models — CatalogItem, Scan, Finding, ScanRun,
VendorVerification, VendorResponse — are GENERATED from `schemas/*.schema.json`
via the codegen pipeline (`app/models/generated/`, native PG enum columns). The
five **internal** models — ItemSource, RateLimit, UploadFile, ArtifactBlob,
ScanEvent — have no JSON-Schema source-of-truth and stay hand-written. Both sets
share the one `Base` (`app/models/base.py`), re-exported by the generated
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
from app.models.artifact_blob import ArtifactBlob
from app.models.base import Base
from app.models.generated import (
    CatalogItem,
    Finding,
    Scan,
    ScanRun,
    VendorResponse,
    VendorVerification,
)
from app.models.item_source import ItemSource
from app.models.rate_limit import RateLimit
from app.models.scan_event import ScanEvent
from app.models.upload_file import UploadFile

__all__ = [
    "ArtifactBlob",
    "Base",
    "CatalogItem",
    "Finding",
    "ItemSource",
    "RateLimit",
    "Scan",
    "ScanEvent",
    "ScanRun",
    "UploadFile",
    "VendorResponse",
    "VendorVerification",
]
