"""Canonical schema version for the Virtual Office payloads (admin + customer).

Single source of truth so BOTH the admin snapshot (/api/platform/office/snapshot)
and the tenant-scoped customer office payload (/api/customer/office) advertise the
SAME contract version to the Unity WebGL client and the 2D/HTML fallback shells.

Per docs/UNITY_OFFICE_API_CONTRACT.md: additive changes keep MAJOR and bump MINOR;
only a breaking change bumps MAJOR (and the shells must then be versioned too).
Unity parses with tolerant JsonUtility, so adding this field is non-breaking —
unknown fields are ignored (see unity/.../OfficeLogicTests.cs malformed-input tests).
"""

from __future__ import annotations

UNITY_OFFICE_SCHEMA_VERSION = "unity-office/1.0"
