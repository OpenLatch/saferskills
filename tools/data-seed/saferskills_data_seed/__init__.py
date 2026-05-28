"""SaferSkills data-seed CLI.

Mirrors the openlatch-platform/tools/data-seed/ pattern. 5 domain groups
plus a doctor:

  - catalog  → publish ~50 fixture items
  - scans    → trigger / list individual scans
  - vendors  → issue verification tokens, redeem, seed responses
  - doctor   → preflight checks
  - purge    → reset DB (local/staging only, hard rails)
"""
