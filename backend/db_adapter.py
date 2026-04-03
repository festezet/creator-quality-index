"""Database adapter — dual SQLite/PostgreSQL support.

Detects DATABASE_URL in environment:
- Present → PostgreSQL via psycopg2 (connection pooling)
- Absent  → SQLite via shared_lib.db
"""
import os
import re

from backend.config import DATABASE_URL, DB_PATH, IS_POSTGRES

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool

    _pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL)
else:
    from shared_lib.db import get_connection


def _convert_placeholders(sql):
    """Convert ? placeholders to %s for PostgreSQL."""
    if not IS_POSTGRES:
        return sql
    result = []
    in_string = False
    quote_char = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_string:
            result.append(ch)
            if ch == quote_char:
                in_string = False
        elif ch in ("'", '"'):
            in_string = True
            quote_char = ch
            result.append(ch)
        elif ch == '?':
            result.append('%s')
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def get_db():
    """Get a database connection."""
    if IS_POSTGRES:
        return _pool.getconn()
    return get_connection(DB_PATH, check_same_thread=False)


def release_db(conn):
    """Release connection back to pool (PostgreSQL) or close (SQLite)."""
    if IS_POSTGRES:
        _pool.putconn(conn)
    else:
        conn.close()


def db_query(sql, params=None, one=False):
    """Execute a SELECT query and return results as list of dicts (or single dict if one=True)."""
    params = params or []
    converted_sql = _convert_placeholders(sql)
    conn = get_db()
    try:
        if IS_POSTGRES:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(converted_sql, params)
            rows = cur.fetchall()
            cur.close()
            result = [dict(r) for r in rows]
        else:
            cur = conn.cursor()
            cur.execute(converted_sql, params)
            columns = [desc[0] for desc in cur.description] if cur.description else []
            raw_rows = cur.fetchall()
            result = [dict(zip(columns, row)) if not hasattr(row, 'keys') else dict(row) for row in raw_rows]
            cur.close()
        if one:
            return result[0] if result else None
        return result
    finally:
        release_db(conn)


def db_execute(sql, params=None):
    """Execute an INSERT/UPDATE/DELETE and commit."""
    params = params or []
    converted_sql = _convert_placeholders(sql)
    conn = get_db()
    try:
        if IS_POSTGRES:
            cur = conn.cursor()
            cur.execute(converted_sql, params)
            conn.commit()
            lastrowid = None
            # Try to get lastrowid for INSERT ... RETURNING
            if cur.description:
                row = cur.fetchone()
                if row:
                    lastrowid = row[0]
            cur.close()
            return lastrowid
        else:
            cur = conn.cursor()
            cur.execute(converted_sql, params)
            conn.commit()
            lastrowid = cur.lastrowid
            cur.close()
            return lastrowid
    finally:
        release_db(conn)


def db_executemany(sql, params_list):
    """Execute a statement with multiple parameter sets."""
    converted_sql = _convert_placeholders(sql)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.executemany(converted_sql, params_list)
        conn.commit()
        cur.close()
    finally:
        release_db(conn)


def db_executescript(script):
    """Execute a multi-statement SQL script (SQLite only, for init)."""
    if IS_POSTGRES:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(script)
            conn.commit()
            cur.close()
        finally:
            release_db(conn)
    else:
        conn = get_connection(DB_PATH)
        conn.executescript(script)
        conn.close()
