import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional

from models import Product, Transaction, TransactionType

DB_PATH = "inventory.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT 'General',
                unit_price REAL NOT NULL DEFAULT 0.0,
                cost_price REAL NOT NULL DEFAULT 0.0,
                quantity_on_hand REAL NOT NULL DEFAULT 0.0,
                reorder_level REAL NOT NULL DEFAULT 10.0,
                reorder_quantity REAL NOT NULL DEFAULT 50.0,
                unit TEXT NOT NULL DEFAULT 'units',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id),
                transaction_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit_price REAL NOT NULL DEFAULT 0.0,
                reference TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_product ON transactions(product_id);
            CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
            CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
        """)


def _row_to_product(row) -> Product:
    return Product(**dict(row))


def _row_to_transaction(row) -> Transaction:
    return Transaction(**dict(row))


# --- Products ---

def create_product(sku, name, description, category, unit_price, cost_price,
                   quantity_on_hand, reorder_level, reorder_quantity, unit) -> Product:
    now = datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO products
               (sku, name, description, category, unit_price, cost_price,
                quantity_on_hand, reorder_level, reorder_quantity, unit, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sku, name, description, category, unit_price, cost_price,
             quantity_on_hand, reorder_level, reorder_quantity, unit, now, now)
        )
        product_id = cur.lastrowid
    return get_product_by_id(product_id)


def get_product_by_id(product_id: int) -> Optional[Product]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _row_to_product(row) if row else None


def get_product_by_sku(sku: str) -> Optional[Product]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        return _row_to_product(row) if row else None


def list_products(category: Optional[str] = None, low_stock_only: bool = False) -> List[Product]:
    with get_conn() as conn:
        query = "SELECT * FROM products"
        params = []
        conditions = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if low_stock_only:
            conditions.append("quantity_on_hand <= reorder_level")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY category, name"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_product(r) for r in rows]


def update_product(product_id: int, **fields) -> Optional[Product]:
    if not fields:
        return get_product_by_id(product_id)
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [product_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE products SET {set_clause} WHERE id = ?", values)
    return get_product_by_id(product_id)


def delete_product(product_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        return cur.rowcount > 0


def adjust_stock(product_id: int, delta: float) -> Optional[Product]:
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE products SET quantity_on_hand = quantity_on_hand + ?, updated_at = ? WHERE id = ?",
            (delta, now, product_id)
        )
    return get_product_by_id(product_id)


def list_categories() -> List[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
        return [r[0] for r in rows]


# --- Transactions ---

def record_transaction(product_id: int, transaction_type: str, quantity: float,
                       unit_price: float, reference: str = "", notes: str = "") -> Transaction:
    now = datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO transactions
               (product_id, transaction_type, quantity, unit_price, reference, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (product_id, transaction_type, quantity, unit_price, reference, notes, now)
        )
        txn_id = cur.lastrowid
    with get_conn() as conn:
        row = conn.execute(
            """SELECT t.*, p.sku AS product_sku, p.name AS product_name
               FROM transactions t JOIN products p ON t.product_id = p.id
               WHERE t.id = ?""",
            (txn_id,)
        ).fetchone()
        return _row_to_transaction(row)


def list_transactions(product_id: Optional[int] = None,
                      transaction_type: Optional[str] = None,
                      limit: int = 50) -> List[Transaction]:
    with get_conn() as conn:
        query = """SELECT t.*, p.sku AS product_sku, p.name AS product_name
                   FROM transactions t JOIN products p ON t.product_id = p.id"""
        params = []
        conditions = []
        if product_id:
            conditions.append("t.product_id = ?")
            params.append(product_id)
        if transaction_type:
            conditions.append("t.transaction_type = ?")
            params.append(transaction_type)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += f" ORDER BY t.created_at DESC LIMIT {limit}"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_transaction(r) for r in rows]


# --- Reports ---

def get_inventory_summary() -> dict:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) AS total_products,
                SUM(quantity_on_hand) AS total_units,
                SUM(quantity_on_hand * cost_price) AS total_value,
                SUM(CASE WHEN quantity_on_hand <= reorder_level THEN 1 ELSE 0 END) AS low_stock_count,
                SUM(CASE WHEN quantity_on_hand = 0 THEN 1 ELSE 0 END) AS out_of_stock_count
            FROM products
        """).fetchone()
        return dict(row)


def get_category_summary() -> List[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                category,
                COUNT(*) AS product_count,
                SUM(quantity_on_hand) AS total_units,
                SUM(quantity_on_hand * cost_price) AS total_value
            FROM products
            GROUP BY category
            ORDER BY total_value DESC
        """).fetchall()
        return [dict(r) for r in rows]
