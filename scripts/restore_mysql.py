#!/usr/bin/env python3
"""
restore_mysql.py — Restore a MySQL database from a .sql.gz backup file.

Cross-platform Python fallback (works on Windows too).
Reads credentials exclusively from DATABASE_URL — no hardcoded values.
Requires explicit confirmation before overwriting the target database.

Required env var:
    DATABASE_URL   mysql+pymysql://user:password@host:port/dbname

Usage:
    python scripts/restore_mysql.py backups/gnaid_db_20260511_020001.sql.gz

    # Skip interactive prompt (CI / automated recovery)
    RESTORE_CONFIRM=yes python scripts/restore_mysql.py <file>
"""

import gzip
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_dotenv(repo_dir: Path) -> None:
    env_file = repo_dir / ".env"
    if not env_file.is_file():
        return
    with env_file.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _parse_database_url(url: str) -> dict:
    normalized = re.sub(r"\+[^:]+(?=://)", "", url)
    parsed = urlparse(normalized)
    host = parsed.hostname or "localhost"
    port = parsed.port or 3306
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    database = parsed.path.lstrip("/").split("?")[0]
    if not database:
        raise ValueError("DATABASE_URL does not contain a database name.")
    return {"host": host, "port": port, "user": user, "password": password, "database": database}


def _find_mysql() -> str:
    exe = shutil.which("mysql")
    if exe:
        return exe
    candidates = [
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
        r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe",
        r"C:\xampp\mysql\bin\mysql.exe",
        r"C:\wamp64\bin\mysql\mysql8.0\bin\mysql.exe",
    ]
    for path in candidates:
        if Path(path).is_file():
            return path
    raise FileNotFoundError(
        "mysql client not found. Install MySQL client tools and ensure they are in PATH."
    )


def _validate_gzip(filepath: Path) -> bool:
    """Return True if the file is a readable gzip archive."""
    try:
        with gzip.open(filepath, "rb") as f:
            f.read(16)
        return True
    except Exception:
        return False


def _confirm(db_name: str, db_host: str, db_port: int, db_user: str,
             backup_file: Path) -> bool:
    """Print warning banner and return True if user confirms. Skippable via env."""
    size_kb = backup_file.stat().st_size // 1024
    line = "─" * 60

    print(f"\n┌{line}┐")
    print(f"│{'  ⚠  DATABASE RESTORE  ⚠':^60}│")
    print(f"├{line}┤")
    print(f"│  {'Target database':<18}: {db_name:<37}│")
    print(f"│  {'Host':<18}: {db_host}:{db_port:<35}│")
    print(f"│  {'Restore user':<18}: {db_user:<37}│")
    print(f"│  {'Backup file':<18}: {backup_file.name:<37}│")
    print(f"│  {'Backup size':<18}: {size_kb} KB{'':<35}│")
    print(f"├{line}┤")
    msg = f"  ALL EXISTING DATA IN '{db_name}' WILL BE OVERWRITTEN."
    print(f"│{msg:<60}│")
    print(f"└{line}┘\n")

    if os.environ.get("RESTORE_CONFIRM", "").lower() == "yes":
        print("[restore] RESTORE_CONFIRM=yes — skipping interactive prompt.")
        return True

    try:
        answer = input(f"Type the database name to confirm restore: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[restore] Aborted.")
        return False

    if answer != db_name:
        print(f"[restore] Aborted — input did not match database name '{db_name}'.")
        return False

    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/restore_mysql.py <path/to/backup.sql.gz>", file=sys.stderr)
        return 1

    backup_file = Path(sys.argv[1]).resolve()

    if not backup_file.is_file():
        print(f"[restore] ERROR: File not found: {backup_file}", file=sys.stderr)
        return 1

    if backup_file.suffix != ".gz" or not backup_file.stem.endswith(".sql"):
        print(f"[restore] ERROR: Expected a .sql.gz file, got: {backup_file.name}", file=sys.stderr)
        return 1

    if not _validate_gzip(backup_file):
        print(f"[restore] ERROR: File is not a valid gzip archive: {backup_file}", file=sys.stderr)
        return 1

    # ── Credentials ──────────────────────────────────────────────────────
    repo_dir = Path(__file__).resolve().parent.parent

    if "DATABASE_URL" not in os.environ:
        _load_dotenv(repo_dir)

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("[restore] ERROR: DATABASE_URL is not set.", file=sys.stderr)
        return 1

    try:
        db = _parse_database_url(database_url)
    except ValueError as exc:
        print(f"[restore] ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        mysql_exe = _find_mysql()
    except FileNotFoundError as exc:
        print(f"[restore] ERROR: {exc}", file=sys.stderr)
        return 1

    # ── Safety confirmation ───────────────────────────────────────────────
    if not _confirm(db["database"], db["host"], db["port"], db["user"], backup_file):
        return 1

    # ── Restore ───────────────────────────────────────────────────────────
    print(f"[restore] Starting restore from: {backup_file}")

    import time
    start = time.monotonic()

    cmd = [
        mysql_exe,
        f"--host={db['host']}",
        f"--port={db['port']}",
        f"--user={db['user']}",
        f"--database={db['database']}",
    ]

    env = os.environ.copy()
    env["MYSQL_PWD"] = db["password"]

    try:
        with gzip.open(backup_file, "rb") as gz:
            sql_bytes = gz.read()

        result = subprocess.run(
            cmd,
            input=sql_bytes,
            env=env,
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        print(f"[restore] ERROR: {exc}", file=sys.stderr)
        return 1

    if result.returncode != 0:
        stderr_msg = result.stderr.decode(errors="replace").strip()
        print(f"[restore] ERROR: mysql exited with code {result.returncode}:\n{stderr_msg}", file=sys.stderr)
        return 1

    elapsed = time.monotonic() - start
    print(f"[restore] Restore complete in {elapsed:.1f}s.")
    print(f"[restore] Database '{db['database']}' on {db['host']}:{db['port']} has been restored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
