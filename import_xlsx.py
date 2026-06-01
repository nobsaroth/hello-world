#!/usr/bin/env python3
"""Import Roast & Co Cambodia April 2026 inventory data from Excel."""

import os
import re
import sys

import openpyxl

import database as db
from models import TransactionType

XLSX_PATH = "/root/.claude/uploads/f905cec1-7b8b-465c-a82d-91dc2334a733/c2762a62-04._Inventory_Report_of_April_2026__Copy.xlsx"

SECTION_HEADERS = {"Manufacturing Items", "Merchandise Items", "Other Items", "Total"}


def eval_formula(val):
    """Evaluate simple arithmetic formula strings like '=10*2'."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str) and val.startswith("="):
        expr = val[1:]
        if re.match(r'^[\d\s\+\-\*\/\.]+$', expr):
            try:
                return float(eval(expr))  # noqa: S307 — only digits/operators
            except Exception:
                pass
    return None


def make_sku(name: str) -> str:
    """Generate a short uppercase SKU from a product name."""
    clean = re.sub(r'[,\(\)_/]', ' ', name)
    clean = re.sub(r'\s+', ' ', clean).strip().upper()
    skip = {'OF', 'AND', 'THE', 'FOR', 'A', 'AN'}
    words = [w for w in clean.split() if w not in skip]
    parts = [w[:5] for w in words[:4]]
    return '-'.join(parts)


def unique_sku(base: str) -> str:
    sku = base
    n = 1
    while db.get_product_by_sku(sku):
        sku = f"{base[:16]}-{n:02d}"
        n += 1
    return sku


def import_products(ws):
    """
    Create products from the Report sheet beginning-inventory columns.
    Returns {item_name: Product}.
    """
    products = {}
    created = skipped = 0

    for row in ws.iter_rows(min_row=7, max_row=68, values_only=True):
        name = row[2]
        if not name or not isinstance(name, str):
            continue
        name = name.strip()
        if name in SECTION_HEADERS or name.startswith('='):
            continue

        packaging = str(row[3]).strip() if row[3] else ""
        item_type  = str(row[4]).strip() if row[4] else ""
        category   = str(row[5]).strip() if row[5] else "General"
        unit       = str(row[6]).strip() if row[6] else "units"
        beg_qty    = float(row[7]) if isinstance(row[7], (int, float)) else 0.0
        beg_val    = float(row[8]) if isinstance(row[8], (int, float)) else 0.0

        cost_price = round(beg_val / beg_qty, 4) if beg_qty > 0 else 0.0
        sku        = unique_sku(make_sku(name))
        desc       = f"{item_type} / {packaging}".strip(" /")

        try:
            p = db.create_product(
                sku=sku,
                name=name,
                description=desc,
                category=category,
                unit_price=0.0,
                cost_price=cost_price,
                quantity_on_hand=beg_qty,
                reorder_level=0.0,
                reorder_quantity=0.0,
                unit=unit,
            )
            if beg_qty > 0:
                db.record_transaction(
                    product_id=p.id,
                    transaction_type=TransactionType.ADJUSTMENT.value,
                    quantity=beg_qty,
                    unit_price=cost_price,
                    reference="OPEN-APR2026",
                    notes="Opening balance April 2026",
                )
            products[name] = p
            created += 1
            flag = "  " if beg_qty > 0 else "  (zero stock)"
            print(f"  + {sku:<25}  {name[:38]:<38}  qty={beg_qty:>8g}  cost=${cost_price:.4f}{flag}")
        except Exception as e:
            print(f"  ! SKIP {name!r}: {e}")
            skipped += 1

    return products, created, skipped


def import_purchases(ws, products):
    """
    Record purchase transactions from the Register Sheet.
    Also adjusts product stock levels.
    """
    imported = skipped = 0
    unmatched = []

    for row in ws.iter_rows(min_row=5, max_row=54, values_only=True):
        row_n    = row[0]
        date_val = row[1]
        name_raw = row[4]
        supplier = str(row[5]).strip() if row[5] else ""
        qty_raw  = row[8]
        total_raw = row[10]
        remark   = str(row[11]).strip() if row[11] else ""

        if not name_raw or not date_val or not isinstance(row_n, int):
            continue

        item_name = str(name_raw).strip()
        qty   = eval_formula(qty_raw)
        total = eval_formula(total_raw)

        if not qty:
            print(f"  ! Row {row_n:>2} '{item_name}': qty unresolvable (raw={qty_raw!r}), skipping")
            skipped += 1
            continue

        cost_per_unit = round(total / qty, 4) if total and qty else 0.0

        # Exact match first, then case-insensitive, then substring
        product = products.get(item_name)
        if not product:
            for pname, p in products.items():
                if item_name.lower() == pname.lower():
                    product = p
                    break
        if not product:
            for pname, p in products.items():
                if item_name.lower() in pname.lower() or pname.lower() in item_name.lower():
                    product = p
                    break

        if not product:
            print(f"  ! Row {row_n:>2} '{item_name}': no matching product — skipped")
            unmatched.append(item_name)
            skipped += 1
            continue

        date_str  = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10]
        reference = f"REG-{row_n:02d}/{date_str}"
        notes_parts = ([f"Supplier: {supplier}"] if supplier else []) + ([remark] if remark else [])
        notes = ". ".join(notes_parts)

        db.adjust_stock(product.id, qty)
        db.record_transaction(
            product_id=product.id,
            transaction_type=TransactionType.PURCHASE.value,
            quantity=qty,
            unit_price=cost_per_unit,
            reference=reference,
            notes=notes,
        )

        imported += 1
        print(f"  + Row {row_n:>2}  {date_str}  {item_name[:35]:<35}  "
              f"qty={qty:>6g}  total=${total or 0:.2f}")

    return imported, skipped, unmatched


def main():
    print(f"Source: {XLSX_PATH}\n")
    wb = openpyxl.load_workbook(XLSX_PATH)

    print("=== Resetting database ===")
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
        print(f"  Removed {db.DB_PATH}")
    db.init_db()
    print("  Fresh database initialised.\n")

    print("=== Importing products from Report sheet (beginning inventory) ===")
    products, p_created, p_skipped = import_products(wb["Report"])
    print(f"\n  Created: {p_created}  Skipped: {p_skipped}\n")

    print("=== Importing April 2026 purchases from Register Sheet ===")
    t_imported, t_skipped, unmatched = import_purchases(wb["Register Sheet"], products)
    print(f"\n  Imported: {t_imported}  Skipped: {t_skipped}")
    if unmatched:
        print(f"  Unmatched items: {', '.join(sorted(set(unmatched)))}")

    print("\n=== Done — Inventory summary ===")
    s = db.get_inventory_summary()
    print(f"  Products    : {s['total_products']}")
    print(f"  Total units : {s['total_units'] or 0:g}")
    print(f"  Total value : ${s['total_value'] or 0:,.2f}")
    print(f"  Zero stock  : {s['out_of_stock_count']}")
    print()
    print("Run: python inventory.py report summary")
    print("     python inventory.py list")
    print("     python inventory.py report valuation")


if __name__ == "__main__":
    main()
