"""Back-compat re-export of the generated `ScanRun` ORM model.

`scan_runs` is now schema-driven: the real ORM class is generated from
`schemas/scan-run-report.schema.json` into `app/models/generated/scan_run.py`.
This shim preserves the historical `from app.models.scan_run import ScanRun`
import path. Relationships are attached in `app/models/_relationships.py`.
"""

from app.models.generated.scan_run import ScanRun

__all__ = ["ScanRun"]
