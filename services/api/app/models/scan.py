"""Back-compat re-exports of the generated `Scan` + `Finding` ORM models and the
hand-written `ScanEvent`.

`scans` + `findings` are now schema-driven (generated from
`schemas/scan-report.schema.json` + `schemas/finding.schema.json` into
`app/models/generated/`). `ScanEvent` has no schema and lives in
`app/models/scan_event.py`. This shim preserves the historical
`from app.models.scan import Scan, Finding, ScanEvent` import path. Relationships
are attached in `app/models/_relationships.py`.
"""

from app.models.generated.finding import Finding
from app.models.generated.scan import Scan
from app.models.scan_event import ScanEvent

__all__ = ["Finding", "Scan", "ScanEvent"]
