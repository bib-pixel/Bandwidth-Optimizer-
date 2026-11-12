"""
Synthetic network snapshot seeder for the Flask bandwidth optimizer.

IMPORTANT:
- This is TEST DATA, not real network measurements.
- Stop the Flask app before running this script.
- It backs up the SQLite database, then replaces ONLY the
  network_snapshots and forecast_evaluations table contents.
- Run with --seed to apply; run with --restore to restore the backup.
- Default DB path is instance/bandwidth_optimizer.db relative to this script.
  Pass --db if your app uses a different SQLite file.

Example:
    python seed_synthetic_network_snapshots.py --seed
    # Start the Flask app and test the dashboard/forecast for at least 15 minutes.
    # Stop Flask, then:
    python seed_synthetic_network_snapshots.py --restore
"""

import argparse
import shutil
import sqlite3
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DB = SCRIPT_DIR / "instance" / "bandwidth_optimizer.db"
DEFAULT_BACKUP = SCRIPT_DIR / "instance" / "bandwidth_optimizer.before_synthetic_test.db"

def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--seed", action="store_true", help="Back up DB and load synthetic snapshots")
    action.add_argument("--restore", action="store_true", help="Restore the DB backup")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP, help="Backup database path")
    parser.add_argument(
        "--csv", type=Path,
        default=SCRIPT_DIR / "synthetic_network_snapshots_7days.csv",
        help="Generated CSV path"
    )
    args = parser.parse_args()
    db_path = args.db.resolve()
    backup_path = args.backup.resolve()

    if args.restore:
        if not backup_path.exists():
            raise SystemExit(f"Backup not found: {backup_path}")
        shutil.copy2(backup_path, db_path)
        print(f"Restored original database from: {backup_path}")
        print("Synthetic test rows and test-time forecast evaluations have been discarded.")
        return

    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    if not args.csv.exists():
        raise SystemExit(f"CSV not found: {args.csv.resolve()}")
    if backup_path.exists():
        raise SystemExit(
            f"Backup already exists: {backup_path}\n"
            "Restore it first or choose another --backup path. Refusing to overwrite it."
        )

    shutil.copy2(db_path, backup_path)
    print(f"Backup created: {backup_path}")

    with args.csv.open("r", encoding="utf-8", newline="") as f:
        import csv
        records = list(csv.DictReader(f))

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        tables = {
            row[0] for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {"network_snapshots", "forecast_evaluations"}
        missing = required - tables
        if missing:
            raise RuntimeError(f"Missing expected table(s): {', '.join(sorted(missing))}")

        # Replace only forecast history/snapshots; other app tables are preserved.
        cur.execute("DELETE FROM forecast_evaluations")
        cur.execute("DELETE FROM network_snapshots")
        cur.executemany(
            """INSERT INTO network_snapshots
               (created_at, throughput_mbps, packet_rate, flow_count, usage_percent)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (r["created_at"], float(r["throughput_mbps"]), float(r["packet_rate"]),
                 int(r["flow_count"]), float(r["usage_percent"]))
                for r in records
            ],
        )
        con.commit()
        print(f"Inserted {len(records):,} synthetic one-minute snapshots.")
        print("The updated test pattern is designed for local time (Asia/Kolkata):")
        print("  10:30–11:00 AM: morning rise")
        print("  1:00–2:00 PM: sustained high traffic; exact daily maximum at 1:30 PM")
        print("  4:00–4:15 PM: shorter afternoon spike")
        print("Run the app, keep the dashboard polling for at least 15 minutes,")
        print("then stop Flask and run this script with --restore.")
    finally:
        con.close()

if __name__ == "__main__":
    main()
