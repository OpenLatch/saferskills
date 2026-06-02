"""Production ORM model registry — Base.metadata sees only these imports.

The W1 codegen at `app/models/generated/` produces 4-column stubs that don't
match the real schema. Phase B (Track B) hand-writes full-column models here
until the SQLAlchemy generator gets full column projection.

Importing this module is sufficient to register every ORM model against
`Base.metadata` (declarative classes self-register on definition).
"""

from app.models.artifact_blob import ArtifactBlob
from app.models.base import Base
from app.models.catalog_item import CatalogItem
from app.models.item_source import ItemSource
from app.models.rate_limit import RateLimit
from app.models.scan import Finding, Scan, ScanEvent
from app.models.scan_run import ScanRun
from app.models.upload_file import UploadFile
from app.models.vendor import VendorResponse, VendorVerification

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
