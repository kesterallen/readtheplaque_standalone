
import sqlite3
import sys

if len(sys.argv) != 3:
    print("must give two args")
    sys.exit(1)

src_file = sys.argv[1]
dst_file = sys.argv[2]

with sqlite3.connect(src_file) as src:
    with sqlite3.connect(dst_file) as dst:
        src.backup(dst)
