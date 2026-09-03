# SPDX-License-Identifier: AGPL-3.0-or-later
"""Registreringssvaret från Hydra måste tåla en klient som validerar det."""

from __future__ import annotations

from memaix_gateway.server import _stada_dcr_svar


# Så här ser Hydras verkliga svar ut — avläst från admin/clients på qronkclawd.
HYDRA_SVAR = {
    "client_id": "056da846-03d1-4074-b96f-d6da70931d68",
    "client_name": "Claude",
    "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
    "grant_types": ["authorization_code", "refresh_token"],
    "scope": "offline_access offline openid",
    "audience": ["https://mcp.jimlov.se/", "https://mcp.jimlov.se"],
    "client_uri": "",
    "policy_uri": "",
    "tos_uri": "",
    "logo_uri": "",
    "owner": "",
    "contacts": None,
    "client_secret_expires_at": 0,
}


def test_osatta_valfria_falt_utelamnas():
    """client_uri: "" gav 'Invalid URL' och contacts: null gav 'expected array'
    i klientens validering, vilket underkände hela registreringen."""
    ut = _stada_dcr_svar(HYDRA_SVAR)

    for falt in ("client_uri", "policy_uri", "tos_uri", "logo_uri", "contacts"):
        assert falt not in ut, f"{falt} skulle ha utelämnats"


def test_verkligt_innehall_ror_vi_inte():
    ut = _stada_dcr_svar(HYDRA_SVAR)

    assert ut["client_id"] == HYDRA_SVAR["client_id"]
    assert ut["redirect_uris"] == HYDRA_SVAR["redirect_uris"]
    assert ut["audience"] == HYDRA_SVAR["audience"]
    # Noll är ett värde, inte frånvaro — får inte städas bort.
    assert ut["client_secret_expires_at"] == 0
    # Tom sträng i ett fält som inte är URL-typat är giltigt och ska stå kvar.
    assert ut["owner"] == ""


def test_en_riktig_url_behalls():
    ut = _stada_dcr_svar({"client_id": "x", "client_uri": "https://claude.ai"})

    assert ut["client_uri"] == "https://claude.ai"


def test_ickeobjekt_passerar_oforandrat():
    """Hydra kan svara med ett felobjekt eller något oväntat; städningen
    får inte förvandla det till något annat."""
    assert _stada_dcr_svar(["a"]) == ["a"]
    assert _stada_dcr_svar(None) is None
