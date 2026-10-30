#!/usr/bin/env python3
"""
Approve all pending plaques in the queue.

Usage:
    python approve_all.py           # preview how many are pending
    python approve_all.py --yes     # approve all without prompting
    python approve_all.py --dry-run # show what would be approved

Run on Fly.io:
    fly ssh console -a readtheplaque-standalone
    python approve_all.py
"""

import argparse
import sys

from database import get_db, init_db


def main():
    parser = argparse.ArgumentParser(description="Approve all pending plaques.")
    parser.add_argument("--count", action="store_true", help="Count plaques")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--dry-run", action="store_true", help="Show pending plaques without approving")
    args = parser.parse_args()

    init_db()

    if args.count:
        with get_db() as db:
            pending = db.execute("SELECT count(*) FROM plaques WHERE approved=0").fetchone()[0]
            approved = db.execute("SELECT count(*) FROM plaques WHERE approved!=0").fetchone()[0]

            print(f"pending {pending}, approved {approved}")
            return

    with get_db() as db:
        pending = db.execute(
            "SELECT id, slug, title, submitted_by, created_at"
            " FROM plaques WHERE approved=0 ORDER BY created_at ASC"
        ).fetchall()

    if not pending:
        print("No pending plaques in the queue.")
        return

    print(f"{len(pending)} plaque(s) pending:\n")
    for p in pending:
        submitter = p["submitted_by"] or "anonymous"
        date = (p["created_at"] or "")[:10]
        print(f"  [{p['id']:4d}]  {p['title'][:50]:<50}  by {submitter:<20}  {date}")

    if args.dry_run:
        print("\nDry run — nothing changed.")
        return

    if not args.yes:
        print()
        answer = input(f"Approve all {len(pending)} plaques? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    with get_db() as db:
        db.execute("UPDATE plaques SET approved=1 WHERE approved=0")

    print(f"\nApproved {len(pending)} plaque(s). ✓")


if __name__ == "__main__":
    main()
