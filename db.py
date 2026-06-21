import os
import secrets
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "splitbot.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def init():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()
    with connect() as conn:
        conn.executescript(schema)
    _migrate()


def _migrate():
    """Idempotent schema upgrades for existing databases."""
    with connect() as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(expenses)").fetchall()]
        if "seq" not in cols:
            try:
                conn.execute("ALTER TABLE expenses ADD COLUMN seq INTEGER")
            except sqlite3.OperationalError:
                return  # added by a concurrent worker; nothing to do
            # Backfill: number each event's expenses 1..N by insertion order.
            ev_ids = [r["event_id"] for r in
                      conn.execute("SELECT DISTINCT event_id FROM expenses").fetchall()]
            for eid in ev_ids:
                rows = conn.execute(
                    "SELECT id FROM expenses WHERE event_id = ? ORDER BY id", (eid,)
                ).fetchall()
                for i, r in enumerate(rows, start=1):
                    conn.execute("UPDATE expenses SET seq = ? WHERE id = ?", (i, r["id"]))


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- members ---

def upsert_member(group_id: str, user_id: str, display_name: str):
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO members(group_id, user_id, display_name)
            VALUES(?, ?, ?)
            ON CONFLICT(group_id, user_id) DO UPDATE SET display_name = excluded.display_name
            """,
            (group_id, user_id, display_name),
        )


def list_members(group_id: str):
    with connect() as conn:
        rows = conn.execute(
            "SELECT user_id, display_name FROM members WHERE group_id = ? ORDER BY display_name",
            (group_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def find_member_by_name(group_id: str, name: str):
    """Return user_id of member with given display_name in group, or None."""
    with connect() as conn:
        row = conn.execute(
            "SELECT user_id FROM members WHERE group_id = ? AND display_name = ?",
            (group_id, name),
        ).fetchone()
    return row["user_id"] if row else None


def add_anon_member(group_id: str, name: str) -> str | None:
    """Create an anonymous member with display_name `name`. Returns user_id, or
    None if `name` is already taken in this group."""
    if find_member_by_name(group_id, name) is not None:
        return None
    anon_id = f"anon:{secrets.token_hex(6)}"
    upsert_member(group_id, anon_id, name)
    return anon_id


def display_name(group_id: str, user_id: str) -> str:
    with connect() as conn:
        row = conn.execute(
            "SELECT display_name FROM members WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
    return row["display_name"] if row else user_id[:6]


# --- events ---

def active_event(group_id: str):
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name FROM events WHERE group_id = ? AND status = 'active'",
            (group_id,),
        ).fetchone()
    return dict(row) if row else None


def create_event(group_id: str, name: str) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO events(group_id, name) VALUES(?, ?)",
            (group_id, name),
        )
        return cur.lastrowid


def close_event(event_id: int):
    with connect() as conn:
        conn.execute(
            "UPDATE events SET status = 'closed' WHERE id = ?",
            (event_id,),
        )


# --- expenses ---

def add_expense(event_id: int, payer_id: str, amount: int,
                shares: list[tuple[str, int]], note: str | None = None) -> int:
    """shares = [(user_id, share_amount), ...]. Returns the per-event seq number."""
    with connect() as conn:
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next FROM expenses WHERE event_id = ?",
            (event_id,),
        ).fetchone()["next"]
        cur = conn.execute(
            "INSERT INTO expenses(event_id, seq, payer_id, amount, note) VALUES(?, ?, ?, ?, ?)",
            (event_id, seq, payer_id, amount, note),
        )
        expense_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO expense_shares(expense_id, user_id, share) VALUES(?, ?, ?)",
            [(expense_id, uid, s) for uid, s in shares],
        )
        return seq


def list_expenses(event_id: int):
    with connect() as conn:
        exps = conn.execute(
            "SELECT id, seq, payer_id, amount, note FROM expenses WHERE event_id = ? ORDER BY seq",
            (event_id,),
        ).fetchall()
        shares = conn.execute(
            """
            SELECT s.expense_id, s.user_id, s.share
            FROM expense_shares s JOIN expenses e ON e.id = s.expense_id
            WHERE e.event_id = ?
            """,
            (event_id,),
        ).fetchall()
    by_exp = {}
    for s in shares:
        by_exp.setdefault(s["expense_id"], []).append((s["user_id"], s["share"]))
    return [
        {
            "id": e["id"],
            "seq": e["seq"],
            "payer_id": e["payer_id"],
            "amount": e["amount"],
            "note": e["note"],
            "shares": by_exp.get(e["id"], []),
        }
        for e in exps
    ]


def delete_expense(event_id: int, seq: int) -> bool:
    """Delete by per-event seq number."""
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM expenses WHERE seq = ? AND event_id = ?",
            (seq, event_id),
        )
        return cur.rowcount > 0


# --- reminders (group-scoped "remember to bring" checklist) ---

def add_reminder(group_id: str, item: str) -> int:
    """Append an item; returns its per-group seq number."""
    with connect() as conn:
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next FROM reminders WHERE group_id = ?",
            (group_id,),
        ).fetchone()["next"]
        conn.execute(
            "INSERT INTO reminders(group_id, seq, item) VALUES(?, ?, ?)",
            (group_id, seq, item),
        )
        return seq


def list_reminders(group_id: str):
    with connect() as conn:
        rows = conn.execute(
            "SELECT seq, item FROM reminders WHERE group_id = ? ORDER BY seq",
            (group_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_reminder(group_id: str, seq: int) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM reminders WHERE group_id = ? AND seq = ?",
            (group_id, seq),
        )
        return cur.rowcount > 0
