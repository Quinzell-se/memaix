# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agentloopens identitetskontext — EN contextvar, ett kontrakt.

Sätts enbart av ToolBridge.call() med användaren från en verifierad
webbsession (samma signerade cookie som /app) — aldrig från requestdata
eller modell-output — och återställs alltid i finally. server._user()
konsulterar den FÖRE OAuth-fallet.

Egen modul (inte server.py) så llm-lagret och dess tester aldrig behöver
dra in MCP-beroendet, och så att kontraktet har exakt en definition.
"""

from __future__ import annotations

import contextvars

AGENT_USER: contextvars.ContextVar = contextvars.ContextVar(
    "memaix_agent_user", default=None
)
