#!/usr/bin/env python3
"""Generera PBKDF2-lösenordshash för memaix login-app.

Kör: python scripts/gen-password-hash.py
"""
import getpass
import hashlib
import os

pw = getpass.getpass("Välj lösenord: ")
pw2 = getpass.getpass("Bekräfta: ")
if pw != pw2:
    raise SystemExit("Lösenorden matchar inte.")

salt = os.urandom(32)
key = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
print(f"\nMEMAIX_LOGIN_PASSWORD_HASH={salt.hex()}:{key.hex()}")
print("\nLägg detta i .env på servern.")
