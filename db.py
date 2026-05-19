import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "splitbot.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def init():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()
    with connect() as conn:
        conn.executescript(schema)


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
    """shares = [(user_id, share_amount), ...]"""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO expenses(event_id, payer_id, amount, note) VALUES(?, ?, ?, ?)",
            (event_id, payer_id, amount, note),
        )
        expense_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO expense_shares(expense_id, user_id, share) VALUES(?, ?, ?)",
            [(expense_id, uid, s) for uid, s in shares],
        )
        return expense_id


def list_expenses(event_id: int):
    with connect() as conn:
        exps = conn.execute(
            "SELECT id, payer_id, amount, note FROM expenses WHERE event_id = ? ORDER BY id",
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
            "payer_id": e["payer_id"],
            "amount": e["amount"],
            "note": e["note"],
            "shares": by_exp.get(e["id"], []),
        }
        for e in exps
    ]


def delete_expense(event_id: int, expense_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM expenses WHERE id = ? AND event_id = ?",
            (expense_id, event_id),
        )
        return cur.rowcount > 0
