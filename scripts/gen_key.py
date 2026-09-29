"""Generate Fernet encryption key and session secret key.

Usage:
    python scripts/gen_key.py
"""

import secrets

from cryptography.fernet import Fernet


def main():
    fernet_key = Fernet.generate_key().decode()
    session_key = secrets.token_urlsafe(32)

    print("Add these to your .env file:\n")
    print(f"TOKEN_ENCRYPTION_KEY={fernet_key}")
    print(f"SESSION_SECRET_KEY={session_key}")


if __name__ == "__main__":
    main()
