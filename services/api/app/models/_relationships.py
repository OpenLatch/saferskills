"""Centralised ORM relationship wiring.

The schema-backed models (CatalogItem / Scan / Finding / ScanRun /
VendorVerification / VendorResponse) are generated from `schemas/` and the
generator emits FK columns only — never `relationship()`s. The hand-written
internal models (ScanEvent / UploadFile) are kept relationship-free in their own
files. This module attaches every cross-model relationship imperatively at import
time (before the mapper configures on first query), preserving the exact
cascade / passive_deletes semantics the hand-written models used so
`delete_run_cascade` + the SSE/upload flows behave identically.

Imported for its side effects by `app/models/__init__.py` after all mapped
classes are defined.
"""

from __future__ import annotations

from sqlalchemy.orm import relationship

from app.models.agent_evidence import AgentEvidence
from app.models.agent_scan_telemetry import AgentScanTelemetry
from app.models.generated.agent_finding import AgentFinding
from app.models.generated.agent_run import AgentRun
from app.models.generated.catalog_item import CatalogItem
from app.models.generated.finding import Finding
from app.models.generated.scan import Scan
from app.models.generated.scan_run import ScanRun
from app.models.generated.vendor_response import VendorResponse
from app.models.generated.vendor_verification import VendorVerification
from app.models.scan_event import ScanEvent
from app.models.upload_file import UploadFile

# ── catalog_item ↔ scans ──────────────────────────────────────────────────────
CatalogItem.scans = relationship(
    "Scan",
    back_populates="catalog_item",
    cascade="all, delete-orphan",
    passive_deletes=True,
)
Scan.catalog_item = relationship("CatalogItem", back_populates="scans")

# ── scan_runs ↔ scans ─────────────────────────────────────────────────────────
ScanRun.scans = relationship("Scan", back_populates="scan_run")
Scan.scan_run = relationship("ScanRun", back_populates="scans")

# ── scans ↔ findings ──────────────────────────────────────────────────────────
Scan.findings = relationship(
    "Finding",
    back_populates="scan",
    cascade="all, delete-orphan",
    passive_deletes=True,
)
Finding.scan = relationship("Scan", back_populates="findings")

# ── scans ↔ scan_events ───────────────────────────────────────────────────────
Scan.events = relationship(
    "ScanEvent",
    back_populates="scan",
    cascade="all, delete-orphan",
    passive_deletes=True,
)
ScanEvent.scan = relationship("Scan", back_populates="events")
# Run-level progress events also reference the run directly (no back-reference).
ScanEvent.scan_run = relationship("ScanRun")

# ── scan_runs ↔ upload_files ──────────────────────────────────────────────────
ScanRun.upload_files = relationship(
    "UploadFile",
    back_populates="scan_run",
    cascade="all, delete-orphan",
    passive_deletes=True,
)
UploadFile.scan_run = relationship("ScanRun", back_populates="upload_files")

# ── vendor_verifications ↔ vendor_responses ───────────────────────────────────
VendorVerification.responses = relationship(
    "VendorResponse",
    back_populates="verification",
    cascade="all, delete-orphan",
    passive_deletes=True,
)
VendorResponse.verification = relationship("VendorVerification", back_populates="responses")

# ── agent_runs ↔ agent_findings ───────────────────────────────────────────────
AgentRun.findings = relationship(
    "AgentFinding",
    back_populates="agent_run",
    cascade="all, delete-orphan",
    passive_deletes=True,
)
AgentFinding.agent_run = relationship("AgentRun", back_populates="findings")

# ── agent_runs ↔ agent_evidence (1:1, CASCADE) ────────────────────────────────
AgentRun.evidence = relationship(
    "AgentEvidence",
    back_populates="agent_run",
    uselist=False,
    cascade="all, delete-orphan",
    passive_deletes=True,
)
AgentEvidence.agent_run = relationship("AgentRun", back_populates="evidence")

# ── agent_runs ↔ agent_scan_telemetry (SET NULL — anonymous aggregate survives) ─
# The FK is `ON DELETE SET NULL`, so the telemetry row is NOT deleted with the
# run (no delete-orphan cascade); the DB nulls `agent_run_id`.
AgentRun.telemetry = relationship(
    "AgentScanTelemetry",
    back_populates="agent_run",
    passive_deletes=True,
)
AgentScanTelemetry.agent_run = relationship("AgentRun", back_populates="telemetry")
