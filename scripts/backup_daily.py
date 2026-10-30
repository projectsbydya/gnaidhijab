#!/usr/bin/env python3
"""
Daily database backup script with compression and retention.

Can be run manually or via cron:
    0 2 * * * cd /root/gnaid && /root/gnaid/venv/bin/python scripts/backup_daily.py >> /var/log/gnaid_backup.log 2>&1

Environment variables required:
    DATABASE_URL - MySQL connection string

Optional:
    BACKUP_DIR - Directory for backups (default: ./backups)
    BACKUP_RETAIN - Number of backups to keep (default: 7)
    BACKUP_S3_BUCKET - Optional S3 bucket for offsite backup
    BACKUP_S3_PREFIX - Prefix for S3 objects (default: gnaid/backups/)
"""

import os
import re
import gzip
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def load_env():
    """Load .env file if DATABASE_URL not set."""
    if os.getenv("DATABASE_URL"):
        return
    
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if not os.getenv(key):
                        os.environ[key] = value.strip().strip('"\'')


def parse_database_url(url: str) -> dict:
    """Parse mysql+pymysql://user:pass@host:port/dbname format."""
    # Remove scheme prefix
    url = re.sub(r"^.*://", "", url)
    
    # Parse user:pass@host:port/db
    match = re.match(r"([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)", url)
    if not match:
        raise ValueError("Invalid DATABASE_URL format")
    
    user, password, host, port, db = match.groups()
    db = db.split("?")[0]  # Remove query params
    
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port or "3306",
        "database": db,
    }


def run_backup(db_config: dict, backup_dir: Path) -> Path:
    """Run mysqldump and create compressed backup."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_name = db_config["database"]
    filename = f"{db_name}_{timestamp}.sql.gz"
    filepath = backup_dir / filename
    
    # Ensure backup directory exists
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Build mysqldump command
    cmd = [
        "mysqldump",
        f"--host={db_config['host']}",
        f"--port={db_config['port']}",
        f"--user={db_config['user']}",
        "--single-transaction",
        "--routines",
        "--triggers",
        db_config["database"],
    ]
    
    env = os.environ.copy()
    env["MYSQL_PWD"] = db_config["password"]
    
    print(f"[backup] Starting backup: {db_name} → {filepath}")
    
    # Run mysqldump, capture stdout, then compress with gzip
    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        if process.returncode != 0:
            raise RuntimeError(f"mysqldump failed: {process.stderr.decode()}")

        with gzip.open(filepath, "wb", compresslevel=9) as gz_file:
            gz_file.write(process.stdout)

        size = filepath.stat().st_size
        size_str = f"{size / 1024 / 1024:.2f} MB" if size > 1024 * 1024 else f"{size / 1024:.1f} KB"
        print(f"[backup] Backup complete: {size_str} written")
        return filepath

    except Exception as e:
        # Clean up partial backup
        if filepath.exists():
            filepath.unlink()
        raise


def cleanup_old_backups(backup_dir: Path, db_name: str, retain: int):
    """Remove old backups beyond retention limit."""
    pattern = f"{db_name}_*.sql.gz"
    backups = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if len(backups) <= retain:
        print(f"[backup] Retention OK — {len(backups)} backup(s) kept")
        return
    
    to_delete = backups[retain:]
    print(f"[backup] Pruning {len(to_delete)} old backup(s):")
    
    for backup_file in to_delete:
        backup_file.unlink()
        print(f"  removed: {backup_file.name}")
    
    remaining = len(backups) - len(to_delete)
    print(f"[backup] Retained: {remaining} backup(s)")


def upload_to_s3(local_path: Path, bucket: str, prefix: str) -> bool:
    """Upload backup to S3 bucket (optional)."""
    try:
        import boto3
        s3 = boto3.client("s3")
        key = f"{prefix}{local_path.name}"
        s3.upload_file(str(local_path), bucket, key)
        print(f"[backup] Uploaded to S3: s3://{bucket}/{key}")
        return True
    except ImportError:
        print("[backup] boto3 not installed, skipping S3 upload")
        return False
    except Exception as e:
        print(f"[backup] S3 upload failed: {e}")
        return False


def main():
    """Main backup routine."""
    load_env()
    
    # Validate environment
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[backup] ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    
    # Parse config
    try:
        db_config = parse_database_url(db_url)
    except ValueError as e:
        print(f"[backup] ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Get settings
    repo_dir = Path(__file__).parent.parent
    backup_dir = Path(os.getenv("BACKUP_DIR", repo_dir / "backups"))
    retain = int(os.getenv("BACKUP_RETAIN", "7"))
    
    # Check dependencies
    if not shutil.which("mysqldump"):
        print("[backup] ERROR: mysqldump not found in PATH", file=sys.stderr)
        sys.exit(1)
    
    # Run backup
    try:
        backup_path = run_backup(db_config, backup_dir)
    except Exception as e:
        print(f"[backup] ERROR: Backup failed: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Cleanup old backups
    cleanup_old_backups(backup_dir, db_config["database"], retain)
    
    # Optional S3 upload
    s3_bucket = os.getenv("BACKUP_S3_BUCKET")
    if s3_bucket:
        s3_prefix = os.getenv("BACKUP_S3_PREFIX", "gnaid/backups/")
        upload_to_s3(backup_path, s3_bucket, s3_prefix)
    
    print(f"[backup] Done at {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
