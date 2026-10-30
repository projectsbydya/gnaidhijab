#!/usr/bin/env python3
"""
backup_mysql.py — Daily compressed MySQL backup with N-day retention.

Cross-platform Python fallback (works on Windows too).
Reads credentials exclusively from environment variables — no hardcoded values.

Required env vars:
    DATABASE_URL   mysql+pymysql://user:password@host:port/dbname

Optional env vars:
    BACKUP_DIR     Destination directory  (default: <repo_root>/backups)
    BACKUP_RETAIN  Number of backups to keep  (default: 7)

Usage:
    # One-off
    python scripts/backup_mysql.py

    # Cron (Linux) — daily at 02:00
    0 2 * * * cd /var/www/gnaid && python scripts/backup_mysql.py >> /var/log/gnaid_backup.log 2>&1

    # Windows Task Scheduler — call this script with pythonw or python.
"""

import gzip
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_dotenv(repo_dir: Path) -> None:
    """Minimal .env loader — only used when DATABASE_URL is not already set."""
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
    """
    Parse DATABASE_URL into components.
    Handles both  mysql+pymysql://...  and plain  mysql://...  schemes.
    Returns dict with keys: host, port, user, password, database.
    """
    # Strip SQLAlchemy driver suffix (e.g. +pymysql)
    normalized = re.sub(r"\+[^:]+(?=://)", "", url)
    parsed = urlparse(normalized)

    host = parsed.hostname or "localhost"
    port = parsed.port or 3306
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    database = parsed.path.lstrip("/").split("?")[0]

    if not database:
        raise ValueError("DATABASE_URL does not contain a database name.")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }


def _find_mysqldump() -> str:
    """Locate mysqldump in PATH or common installation directories."""
    exe = shutil.which("mysqldump")
    if exe:
        return exe

    # Common Windows MySQL install paths
    candidates = [
        r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
        r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysqldump.exe",
        r"C:\xampp\mysql\bin\mysqldump.exe",
        r"C:\wamp64\bin\mysql\mysql8.0\bin\mysqldump.exe",
    ]
    for path in candidates:
        if Path(path).is_file():
            return path

    raise FileNotFoundError(
        "mysqldump not found. Install MySQL client tools and ensure they are in PATH."
    )


def _prune_old_backups(backup_dir: Path, db_name: str, retain: int) -> None:
    """Delete the oldest backups beyond the retention limit."""
    pattern = f"{db_name}_*.sql.gz"
    files = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    to_delete = files[retain:]
    for f in to_delete:
        print(f"[backup] Removing old backup: {f.name}")
        f.unlink()
    if not to_delete:
        print("[backup] Retention OK — no old backups to prune.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    repo_dir = Path(__file__).resolve().parent.parent

    # Load .env only if DATABASE_URL not already in environment
    if "DATABASE_URL" not in os.environ:
        _load_dotenv(repo_dir)

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("[backup] ERROR: DATABASE_URL is not set.", file=sys.stderr)
        return 1

    try:
        db = _parse_database_url(database_url)
    except ValueError as exc:
        print(f"[backup] ERROR: {exc}", file=sys.stderr)
        return 1

    backup_dir = Path(os.environ.get("BACKUP_DIR", repo_dir / "backups"))
    backup_dir.mkdir(parents=True, exist_ok=True)

    retain = int(os.environ.get("BACKUP_RETAIN", "7"))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{db['database']}_{timestamp}.sql.gz"
    filepath = backup_dir / filename

    try:
        mysqldump = _find_mysqldump()
    except FileNotFoundError as exc:
        print(f"[backup] ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"[backup] Starting backup: {db['database']} → {filepath}")

    cmd = [
        mysqldump,
        f"--host={db['host']}",
        f"--port={db['port']}",
        f"--user={db['user']}",
        "--single-transaction",
        "--routines",
        "--triggers",
        
        db["database"],
    ]

    env = os.environ.copy()
    env["MYSQL_PWD"] = db["password"]  # avoids password on CLI / in process list

    try:
        result = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr_msg = exc.stderr.decode(errors="replace").strip()
        print(f"[backup] ERROR: mysqldump failed:\n{stderr_msg}", file=sys.stderr)
        # Remove partial file if it was created
        filepath.unlink(missing_ok=True)
        return 1

    # Compress the dump
    with gzip.open(filepath, "wb", compresslevel=9) as gz_file:
        gz_file.write(result.stdout)

    size_kb = filepath.stat().st_size // 1024
    print(f"[backup] Backup complete: {size_kb} KB written.")

    # Prune old backups
    _prune_old_backups(backup_dir, db["database"], retain)

    remaining = len(list(backup_dir.glob(f"{db['database']}_*.sql.gz")))
    print(f"[backup] Done. Backups retained: {remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
