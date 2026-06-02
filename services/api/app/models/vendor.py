"""Back-compat re-exports of the generated `VendorVerification` + `VendorResponse`
ORM models.

Both are now schema-driven (generated from
`schemas/vendor-verification.schema.json` + `schemas/vendor-response.schema.json`
into `app/models/generated/`). This shim preserves the historical
`from app.models.vendor import VendorResponse, VendorVerification` import path.
Relationships are attached in `app/models/_relationships.py`.
"""

from app.models.generated.vendor_response import VendorResponse
from app.models.generated.vendor_verification import VendorVerification

__all__ = ["VendorResponse", "VendorVerification"]
