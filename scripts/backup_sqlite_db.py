
from sqlite3 import connect
import sys

if len(sys.argv) != 3:
    print("must give two args")
    sys.exit(1)

src_file = sys.argv[1]
dst_file = sys.argv[2]

with connect(src_file) as src, connect(dst_file) as dst:
    src.backup(dst)
