#!/usr/bin/env python3
"""
backup_uploads.py — Daily compressed uploads backup with N-day retention.

Cross-platform Python fallback (works on Windows too, no tar/bash required).
Reads source paths exclusively from environment variables — no hardcoded values.

Env vars honoured (same defaults as config.py):
    PRODUCT_UPLOAD_FOLDER   default: <repo>/static/uploads/products
    BANNER_UPLOAD_FOLDER    default: <repo>/static/images/banners
    VIDEO_UPLOAD_FOLDER     default: <repo>/static/videos

Optional:
    UPLOADS_BACKUP_DIR      Destination directory  (default: <repo>/backups/uploads)
    BACKUP_RETAIN           Archives to keep        (default: 7)

Usage:
    python scripts/backup_uploads.py

    # Cron (Linux) — daily at 03:00
    0 3 * * * cd /var/www/gnaid && python scripts/backup_uploads.py >> /var/log/gnaid_uploads_backup.log 2>&1
"""

import os
import sys
import tarfile
from datetime import datetime
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_dotenv(repo_dir: Path) -> None:
    """Minimal .env loader — sets env vars that are not already present."""
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


def _prune_old_archives(backup_dir: Path, retain: int) -> None:
    """Delete the oldest archives beyond the retention limit."""
    files = sorted(
        backup_dir.glob("uploads_*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    to_delete = files[retain:]
    for f in to_delete:
        print(f"[backup-uploads] Removing old archive: {f.name}")
        f.unlink()
    if not to_delete:
        print("[backup-uploads] Retention OK — no old archives to prune.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    repo_dir = Path(__file__).resolve().parent.parent

    _load_dotenv(repo_dir)

    # ── Source directories (mirror config.py defaults) ────────────────────
    candidates = {
        "PRODUCT_UPLOAD_FOLDER": repo_dir / "static" / "uploads" / "products",
        "BANNER_UPLOAD_FOLDER":  repo_dir / "static" / "images" / "banners",
        "VIDEO_UPLOAD_FOLDER":   repo_dir / "static" / "videos",
    }

    source_dirs: list[Path] = []
    for env_key, default_path in candidates.items():
        raw = os.environ.get(env_key, "")
        resolved = Path(raw) if raw else default_path
        if resolved.is_dir():
            source_dirs.append(resolved)
        else:
            print(f"[backup-uploads] WARN: directory not found, skipping: {resolved}")

    if not source_dirs:
        print("[backup-uploads] ERROR: No upload directories found. Nothing to back up.", file=sys.stderr)
        return 1

    # ── Destination ───────────────────────────────────────────────────────
    raw_dest = os.environ.get("UPLOADS_BACKUP_DIR", "")
    backup_dir = Path(raw_dest) if raw_dest else repo_dir / "backups" / "uploads"
    backup_dir.mkdir(parents=True, exist_ok=True)

    retain = int(os.environ.get("BACKUP_RETAIN", "7"))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"uploads_{timestamp}.tar.gz"
    filepath = backup_dir / filename

    # ── Create archive ────────────────────────────────────────────────────
    print(f"[backup-uploads] Archiving {len(source_dirs)} director(ies) → {filepath}")
    for d in source_dirs:
        print(f"  + {d}")

    try:
        with tarfile.open(filepath, "w:gz", compresslevel=9) as tar:
            for source_dir in source_dirs:
                # Store paths relative to repo_dir for portability
                try:
                    arcname = source_dir.relative_to(repo_dir)
                except ValueError:
                    # Source outside repo — use bare directory name
                    arcname = Path(source_dir.name)
                tar.add(source_dir, arcname=str(arcname))
    except Exception as exc:
        print(f"[backup-uploads] ERROR: Failed to create archive: {exc}", file=sys.stderr)
        filepath.unlink(missing_ok=True)
        return 1

    size_kb = filepath.stat().st_size // 1024
    print(f"[backup-uploads] Archive complete: {size_kb} KB written.")

    # ── Retention ─────────────────────────────────────────────────────────
    _prune_old_archives(backup_dir, retain)

    remaining = len(list(backup_dir.glob("uploads_*.tar.gz")))
    print(f"[backup-uploads] Done. Archives retained: {remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
