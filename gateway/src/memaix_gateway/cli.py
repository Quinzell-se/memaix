# SPDX-License-Identifier: AGPL-3.0-or-later
"""Admin CLI: python -m memaix_gateway.cli <command>.

Commands:
  hash-password  — generate a PBKDF2-HMAC-SHA256 password hash in the
                   salt_hex:key_hex format that login-app/auth.py and the
                   board UI verify against (200 000 iterations). Paste the
                   output into acl.yaml (users.<id>.password_hash) or set it
                   as MEMAIX_LOGIN_PASSWORD_HASH_<USER>.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import secrets
import sys

# Must match login-app/auth.py::pbkdf2_check and board/routes.py::_verify_password.
_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Return salt_hex:key_hex for *password* (PBKDF2-HMAC-SHA256)."""
    if salt is None:
        salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{derived.hex()}"


def _cmd_hash_password() -> int:
    pw = getpass.getpass("Lösenord: ")
    confirm = getpass.getpass("Bekräfta: ")
    if pw != confirm:
        print("Lösenorden matchar inte.", file=sys.stderr)
        return 1
    if not pw:
        print("Tomt lösenord vägras.", file=sys.stderr)
        return 1
    print(hash_password(pw))
    print(
        "\nKlistra in under users.<id>.password_hash i acl.yaml,\n"
        "eller sätt MEMAIX_LOGIN_PASSWORD_HASH_<USER> i .env",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m memaix_gateway.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hash-password", help="generate a PBKDF2 password hash for acl.yaml/.env")
    args = parser.parse_args(argv)

    if args.command == "hash-password":
        return _cmd_hash_password()
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
