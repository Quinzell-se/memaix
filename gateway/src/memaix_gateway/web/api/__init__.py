# SPDX-License-Identifier: AGPL-3.0-or-later
"""JSON endpoints for the web-UI — thin HTTP layers over the tool functions.

Invariant (FEATURE-WEB-UI-MVP.md): each endpoint does HTTP parsing, role
checks and JSON serialization ONLY. Business logic lives in tools/*.
"""
