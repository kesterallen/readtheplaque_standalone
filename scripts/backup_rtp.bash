
# Run sqlite database backup on fly.io server
fly ssh console -C "python scripts/backup_sqlite_db.py /data/plaques.db /data/safe_backup-plaques.db" -a readtheplaque-standalone 

# Copy backup file to local
fly sftp get -a readtheplaque-standalone /data/safe_backup-plaques.db ./safe_backup-plaques.db

# Copy fly.io:/data to local
fly ssh console -C "tar czvf - -C /data" -a readtheplaque-standalone > data_volume_backup.tgz

