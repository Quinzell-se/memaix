# SPDX-License-Identifier: AGPL-3.0-or-later
"""Web-UI app shell (/app) — Starlette routes, pages and static assets.

Lives beside board/ (FEATURE-WEB-UI-FOUNDATION.md): board keeps its API routes
untouched; this package provides the dark app shell, the /app pages and the
/app/api/* JSON endpoints the pages consume.
"""
