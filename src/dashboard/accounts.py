"""Dashboard accounts (FR6).

Accounts are created by an administrator with this command; there is no
self-registration, and no part of the dashboard can change roles. Passwords are
stored only as salted scrypt hashes in outputs/dashboard/accounts.json, which git
ignores. Signing in grants no role by itself: only accounts given the
approved-staff role may upload course files.

  python -m src.dashboard.accounts add NAME --role approved_staff
  python -m src.dashboard.accounts add NAME            (may view, may not upload)
  python -m src.dashboard.accounts list | roles NAME --role ... | password NAME | disable NAME | enable NAME
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path

from src.common import ROOT, read_json, write_json

DEFAULT_ACCOUNTS = ROOT / "outputs" / "dashboard" / "accounts.json"
STAFF_ROLE = "approved_staff"  # May upload course files.
NAME = re.compile(r"[a-z0-9][a-z0-9._-]{1,31}")
ROLE = re.compile(r"[a-z][a-z_]{1,31}")
MIN_PASSWORD = 8
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
# Compared against when the account does not exist, so both cases take similar time.
_DUMMY_HASH = "scrypt$" + "00" * 16 + "$" + "00" * 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${hashlib.scrypt(password.encode(), salt=salt, **SCRYPT).hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT).hex()
    except ValueError:
        return False
    return hmac.compare_digest(candidate, digest)


class AccountStore:
    def __init__(self, path: Path = DEFAULT_ACCOUNTS):
        self.path = Path(path)

    def _load(self) -> dict:
        return read_json(self.path)["accounts"] if self.path.exists() else {}

    def _save(self, accounts: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json(self.path, {"schema_version": 1, "accounts": accounts})
        os.chmod(self.path, 0o600)

    @staticmethod
    def _roles(roles: list[str]) -> list[str]:
        bad = [r for r in roles if not ROLE.fullmatch(r)]
        if bad:
            raise ValueError(f"Invalid role name(s): {bad}; use lowercase letters and underscores")
        return sorted(set(roles))

    def add(self, username: str, password: str, roles: list[str]) -> None:
        if not NAME.fullmatch(username):
            raise ValueError("Usernames are 2-32 lowercase letters, digits, dots, dashes or underscores")
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"Passwords need at least {MIN_PASSWORD} characters")
        accounts = self._load()
        if username in accounts:
            raise ValueError(f"Account {username!r} already exists")
        accounts[username] = {"password": hash_password(password), "roles": self._roles(roles), "active": True}
        self._save(accounts)

    def _update(self, username: str, **changes) -> None:
        accounts = self._load()
        if username not in accounts:
            raise ValueError(f"No account {username!r}")
        accounts[username].update(changes)
        self._save(accounts)

    def set_roles(self, username: str, roles: list[str]) -> None:
        self._update(username, roles=self._roles(roles))

    def set_password(self, username: str, password: str) -> None:
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"Passwords need at least {MIN_PASSWORD} characters")
        self._update(username, password=hash_password(password))

    def set_active(self, username: str, active: bool) -> None:
        self._update(username, active=active)

    def get(self, username: str) -> dict | None:
        """The current account as {username, roles}, or None if it does not exist or is disabled."""
        account = self._load().get(username)
        if not account or not account.get("active"):
            return None
        return {"username": username, "roles": list(account["roles"])}

    def authenticate(self, username: str, password: str) -> dict | None:
        account = self._load().get(username)
        valid = check_password(password, account["password"] if account else _DUMMY_HASH)
        return self.get(username) if valid and account else None

    def summary(self) -> list[dict]:
        return [{"username": u, "roles": a["roles"], "active": a["active"]} for u, a in sorted(self._load().items())]


def ask_password() -> str:
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise ValueError("Passwords do not match")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--accounts", type=Path, default=DEFAULT_ACCOUNTS)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("add", "roles"):
        command = commands.add_parser(name)
        command.add_argument("username")
        command.add_argument("--role", action="append", default=[], help=f"Repeatable; {STAFF_ROLE} may upload")
    for name in ("password", "disable", "enable"):
        commands.add_parser(name).add_argument("username")
    commands.add_parser("list")
    args = parser.parse_args()
    store = AccountStore(args.accounts)
    try:
        if args.command == "add":
            store.add(args.username, ask_password(), args.role)
        elif args.command == "roles":
            store.set_roles(args.username, args.role)
        elif args.command == "password":
            store.set_password(args.username, ask_password())
        elif args.command in ("disable", "enable"):
            store.set_active(args.username, args.command == "enable")
        for account in store.summary():
            print(f"{account['username']:<20} {'active' if account['active'] else 'disabled':<9} {', '.join(account['roles']) or '(no roles)'}")
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
