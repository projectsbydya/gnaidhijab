# Database Backup System

## Overview
Automated daily backups with 7-day retention for MySQL database.

## Features
- ✅ Daily compressed backups (gzip)
- ✅ 7-day retention (configurable)
- ✅ Automatic old backup cleanup
- ✅ Optional S3 upload support
- ✅ Both Bash and Python scripts available

## Setup

### Option 1: Automated Setup (Recommended)
```bash
cd /root/gnaid
sudo bash scripts/setup_cron.sh
```

### Option 2: Manual Cron Setup
```bash
# Edit crontab
crontab -e

# Add this line (runs daily at 02:00):
0 2 * * * cd /root/gnaid && /root/gnaid/venv/bin/python scripts/backup_daily.py >> /var/log/gnaid_backup.log 2>&1
```

### Option 3: Using Bash Script
```bash
# Add to crontab:
0 2 * * * cd /root/gnaid && source .env && bash scripts/backup_mysql.sh >> /var/log/gnaid_backup.log 2>&1
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Required | MySQL connection string |
| `BACKUP_DIR` | `./backups` | Where backups are stored |
| `BACKUP_RETAIN` | `7` | Number of backups to keep |
| `BACKUP_S3_BUCKET` | None | Optional S3 bucket for offsite |
| `BACKUP_S3_PREFIX` | `gnaid/backups/` | S3 object prefix |

## Backup Location

Backups are stored in:
```
/root/gnaid/backups/
├── gnaid_20240601_020000.sql.gz
├── gnaid_20240602_020000.sql.gz
└── ...
```

## Restore from Backup

```bash
# Extract and restore
cd /root/gnaid
gunzip -c backups/gnaid_20240601_020000.sql.gz | mysql -u user -p gnaid

# Or using environment:
source .env
mysql -u $(echo $DATABASE_URL | grep -oP '(?<=://)[^:]+') -p gnaid < <(gunzip -c backups/gnaid_*.sql.gz | tail -1)
```

## Monitoring

Check backup status:
```bash
# View recent backup log
tail -f /var/log/gnaid_backup.log

# List recent backups
ls -lth /root/gnaid/backups/

# Check backup sizes
du -sh /root/gnaid/backups/*
```

## Troubleshooting

### Backup fails with "mysqldump not found"
```bash
sudo apt install mysql-client
```

### Permission denied to log file
```bash
sudo touch /var/log/gnaid_backup.log
sudo chmod 666 /var/log/gnaid_backup.log
```

### Test backup manually
```bash
cd /root/gnaid
source .env
python scripts/backup_daily.py
```

## S3 Upload (Optional)

To enable S3 backup upload:
```bash
# Install boto3
pip install boto3

# Add to .env
BACKUP_S3_BUCKET=my-backup-bucket
BACKUP_S3_PREFIX=gnaid/production/
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_REGION=ap-southeast-1
```

## Security
- Backups are compressed with gzip (compressed, not encrypted)
- Store backups on separate disk/location for disaster recovery
- Consider encrypting backups if they contain sensitive data
- Use S3 with server-side encryption for offsite backups
