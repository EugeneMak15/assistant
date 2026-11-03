"""Merge post-snapshot conversations from the old VPS without losing new-VPS chats."""

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3


ROOT = Path("/opt/assistant")
LIVE = ROOT / "products.db"
SOURCE = ROOT / "_migration_stage" / "_migration_products.db"
OLD_NOTES = ROOT / "_migration_stage" / "_migration_annotations.db"


def history(row):
    return json.loads(row["history_json"] or "[]")


def main():
    if not SOURCE.is_file():
        raise SystemExit("Missing old-server SQLite snapshot")
    source = sqlite3.connect(SOURCE)
    source.row_factory = sqlite3.Row
    live = sqlite3.connect(LIVE, timeout=30)
    live.row_factory = sqlite3.Row
    try:
        conflicts = []
        for old in source.execute("SELECT session_id,history_json FROM chat_state"):
            current = live.execute("SELECT history_json FROM chat_state WHERE session_id=?", (old["session_id"],)).fetchone()
            if not current:
                continue
            old_history, new_history = history(old), history(current)
            if old_history[:len(new_history)] != new_history and new_history[:len(old_history)] != old_history:
                conflicts.append(old["session_id"])
        if conflicts:
            raise SystemExit("Divergent sessions require manual review: " + ", ".join(conflicts))

        backups = ROOT / "_migration_backups"
        backups.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backups / f"new-before-merge-{stamp}.db"
        backup_conn = sqlite3.connect(backup_path)
        live.backup(backup_conn)
        backup_conn.close()

        inserted = updated = usage_added = notes_added = 0
        live.execute("BEGIN IMMEDIATE")
        for old in source.execute("SELECT * FROM chat_state"):
            sid = old["session_id"]
            current = live.execute("SELECT * FROM chat_state WHERE session_id=?", (sid,)).fetchone()
            use_old = not current or len(history(old)) > len(history(current))
            if not current:
                live.execute("INSERT INTO chat_state(session_id,scenario_json,history_json,updated_at) VALUES (?,?,?,?)", tuple(old))
                inserted += 1
            elif use_old:
                live.execute("UPDATE chat_state SET scenario_json=?,history_json=?,updated_at=? WHERE session_id=?",
                             (old["scenario_json"], old["history_json"], old["updated_at"], sid))
                updated += 1
            for table, column in (("chat_results", "results_json"), ("chat_session_fields", "fields_json")):
                old_row = source.execute(f"SELECT {column} FROM {table} WHERE session_id=?", (sid,)).fetchone()
                if not old_row:
                    continue
                new_row = live.execute(f"SELECT {column} FROM {table} WHERE session_id=?", (sid,)).fetchone()
                if not new_row or use_old or (table == "chat_results" and len(json.loads(old_row[0])) > len(json.loads(new_row[0]))):
                    live.execute(f"INSERT INTO {table}(session_id,{column}) VALUES (?,?) ON CONFLICT(session_id) DO UPDATE SET {column}=excluded.{column}",
                                 (sid, old_row[0]))

        fields = "session_id,model,prompt_tokens,cached_tokens,cache_write_tokens,completion_tokens,estimated_cost_usd,created_at"
        existing = Counter(tuple(row) for row in live.execute(f"SELECT {fields} FROM chat_usage"))
        for row in source.execute(f"SELECT {fields} FROM chat_usage"):
            values = tuple(row)
            if existing[values]:
                existing[values] -= 1
            else:
                live.execute(f"INSERT INTO chat_usage({fields}) VALUES (?,?,?,?,?,?,?,?)", values)
                usage_added += 1
        live.commit()

        if OLD_NOTES.is_file():
            old_notes = sqlite3.connect(OLD_NOTES)
            new_notes = sqlite3.connect(ROOT / "debug_annotations.db")
            try:
                for row in old_notes.execute("SELECT * FROM annotated_sessions"):
                    cursor = new_notes.execute("INSERT OR IGNORE INTO annotated_sessions VALUES (?,?,?,?,?,?,?)", row)
                    notes_added += cursor.rowcount
                new_notes.commit()
            finally:
                old_notes.close()
                new_notes.close()
        print(f"Merged: {inserted} sessions added, {updated} updated, {usage_added} usage rows, {notes_added} annotations. Backup: {backup_path}")
    finally:
        source.close()
        live.close()


if __name__ == "__main__":
    main()
