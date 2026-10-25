#
# Run this script on the local machine you want to back up to
#
set -x
set -e

TEMPORARY_BACKUP_FILE="/data/safe_backup-plaques.db"
LOCAL_BACKUP_FILE="./safe_backup-plaques.db"

# Run sqlite database python backup script on fly.io server via "fly ssh console"
fly ssh console -a readtheplaque-standalone -C "rm -f $TEMPORARY_BACKUP_FILE"
fly ssh console -a readtheplaque-standalone -C "python scripts/backup_sqlite_db.py /data/plaques.db $TEMPORARY_BACKUP_FILE"

# SFTP Copy backup file to local
mv $LOCAL_BACKUP_FILE $LOCAL_BACKUP_FILE.old
fly sftp    get -a readtheplaque-standalone $TEMPORARY_BACKUP_FILE $LOCAL_BACKUP_FILE
fly ssh console -a readtheplaque-standalone -C "rm -f $TEMPORARY_BACKUP_FILE"

# Copy fly.io:/data to local -- tar the /data volume, stream to STDOUT and direct that to a local file
fly ssh console -a readtheplaque-standalone -C "tar cvfz - /data" > data_volume_backup.tgz

