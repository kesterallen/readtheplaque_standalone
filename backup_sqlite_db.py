
import sqlite3

src = sqlite3.connect('/data/plaques.db')
dst = sqlite3.connect('/data/safe_backup-plaques.db')
src.backup(dst)
dst.close()
src.close()
