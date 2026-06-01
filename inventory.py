#!/usr/bin/env python3
"""Inventory Control System - Command Line Interface"""

import argparse
import sys
from typing import Optional

import database as db
from models import TransactionType


# --- Formatting helpers ---

def _fmt_currency(value: float) -> str:
    return f"${value:,.2f}"


def _fmt_row(values: list, widths: list) -> str:
    parts = []
    for v, w in zip(values, widths):
        s = str(v)
        parts.append(s[:w].ljust(w) if w > 0 else s)
    return "  ".join(parts)


def _print_table(headers: list, rows: list, widths: list):
    sep = "  ".join("-" * w for w in widths)
    print(_fmt_row(headers, widths))
    print(sep)
    for row in rows:
        print(_fmt_row(row, widths))


# --- Product commands ---

def cmd_add(args):
    existing = db.get_product_by_sku(args.sku)
    if existing:
        print(f"Error: SKU '{args.sku}' already exists (ID {existing.id}).")
        sys.exit(1)

    product = db.create_product(
        sku=args.sku,
        name=args.name,
        description=args.description or "",
        category=args.category or "General",
        unit_price=args.unit_price,
        cost_price=args.cost_price,
        quantity_on_hand=args.quantity or 0,
        reorder_level=args.reorder_level,
        reorder_quantity=args.reorder_quantity,
        unit=args.unit,
    )
    print(f"Added product: [{product.id}] {product.sku} - {product.name}")


def cmd_update(args):
    product = _resolve_product(args.product)
    fields = {}
    for attr in ("name", "description", "category", "unit_price", "cost_price",
                 "reorder_level", "reorder_quantity", "unit"):
        val = getattr(args, attr, None)
        if val is not None:
            fields[attr] = val

    if not fields:
        print("Nothing to update. Use --name, --category, --unit-price, etc.")
        sys.exit(1)

    updated = db.update_product(product.id, **fields)
    print(f"Updated product: [{updated.id}] {updated.sku} - {updated.name}")


def cmd_delete(args):
    product = _resolve_product(args.product)
    if not args.yes:
        confirm = input(f"Delete '{product.name}' ({product.sku})? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return
    if db.delete_product(product.id):
        print(f"Deleted product {product.sku}.")
    else:
        print("Error: product not found.")
        sys.exit(1)


def cmd_show(args):
    product = _resolve_product(args.product)
    print(f"\n{'='*50}")
    print(f"  {product.name} ({product.sku})")
    print(f"{'='*50}")
    print(f"  ID          : {product.id}")
    print(f"  Category    : {product.category}")
    print(f"  Description : {product.description or '—'}")
    print(f"  Unit        : {product.unit}")
    print(f"  Cost Price  : {_fmt_currency(product.cost_price)}")
    print(f"  Unit Price  : {_fmt_currency(product.unit_price)}")
    print(f"  On Hand     : {product.quantity_on_hand} {product.unit}")
    print(f"  Stock Value : {_fmt_currency(product.stock_value)}")
    print(f"  Reorder At  : {product.reorder_level} {product.unit}")
    print(f"  Reorder Qty : {product.reorder_quantity} {product.unit}")
    status = "LOW STOCK" if product.is_low_stock else "OK"
    print(f"  Status      : {status}")
    print(f"  Created     : {product.created_at[:19]}")
    print(f"  Updated     : {product.updated_at[:19]}")
    print()


def cmd_list(args):
    products = db.list_products(
        category=args.category,
        low_stock_only=args.low_stock,
    )
    if not products:
        print("No products found.")
        return

    headers = ["ID", "SKU", "Name", "Category", "On Hand", "Unit", "Cost", "Price", "Status"]
    widths = [4, 12, 25, 15, 8, 6, 10, 10, 10]
    print()
    _print_table(headers, [
        [
            p.id, p.sku, p.name, p.category,
            p.quantity_on_hand, p.unit,
            _fmt_currency(p.cost_price),
            _fmt_currency(p.unit_price),
            "LOW" if p.is_low_stock else "OK",
        ]
        for p in products
    ], widths)
    print(f"\n{len(products)} product(s)")


# --- Stock commands ---

def cmd_receive(args):
    product = _resolve_product(args.product)
    updated = db.adjust_stock(product.id, args.quantity)
    db.record_transaction(
        product_id=product.id,
        transaction_type=TransactionType.PURCHASE.value,
        quantity=args.quantity,
        unit_price=args.price or product.cost_price,
        reference=args.reference or "",
        notes=args.notes or "",
    )
    print(f"Received {args.quantity} {product.unit} of {product.sku}. "
          f"New stock: {updated.quantity_on_hand}")


def cmd_sell(args):
    product = _resolve_product(args.product)
    if product.quantity_on_hand < args.quantity:
        print(f"Error: insufficient stock. Available: {product.quantity_on_hand} {product.unit}.")
        sys.exit(1)
    updated = db.adjust_stock(product.id, -args.quantity)
    db.record_transaction(
        product_id=product.id,
        transaction_type=TransactionType.SALE.value,
        quantity=args.quantity,
        unit_price=args.price or product.unit_price,
        reference=args.reference or "",
        notes=args.notes or "",
    )
    print(f"Sold {args.quantity} {product.unit} of {product.sku}. "
          f"Remaining stock: {updated.quantity_on_hand}")
    if updated.is_low_stock:
        print(f"  WARNING: Stock is at or below reorder level ({product.reorder_level}).")


def cmd_adjust(args):
    product = _resolve_product(args.product)
    delta = args.quantity - product.quantity_on_hand
    updated = db.adjust_stock(product.id, delta)
    db.record_transaction(
        product_id=product.id,
        transaction_type=TransactionType.ADJUSTMENT.value,
        quantity=delta,
        unit_price=0.0,
        reference=args.reference or "",
        notes=args.notes or f"Manual adjustment to {args.quantity}",
    )
    print(f"Adjusted {product.sku} stock: {product.quantity_on_hand} -> {updated.quantity_on_hand}")


def cmd_return(args):
    product = _resolve_product(args.product)
    updated = db.adjust_stock(product.id, args.quantity)
    db.record_transaction(
        product_id=product.id,
        transaction_type=TransactionType.RETURN.value,
        quantity=args.quantity,
        unit_price=args.price or product.unit_price,
        reference=args.reference or "",
        notes=args.notes or "",
    )
    print(f"Returned {args.quantity} {product.unit} of {product.sku}. "
          f"New stock: {updated.quantity_on_hand}")


# --- History ---

def cmd_history(args):
    product_id = None
    if args.product:
        product = _resolve_product(args.product)
        product_id = product.id

    transactions = db.list_transactions(
        product_id=product_id,
        transaction_type=args.type,
        limit=args.limit,
    )

    if not transactions:
        print("No transactions found.")
        return

    headers = ["ID", "Date", "SKU", "Product", "Type", "Qty", "Price", "Reference"]
    widths = [5, 19, 12, 20, 12, 6, 10, 15]
    print()
    _print_table(headers, [
        [
            t.id,
            t.created_at[:19],
            t.product_sku,
            t.product_name,
            t.transaction_type,
            t.quantity,
            _fmt_currency(t.unit_price),
            t.reference or "—",
        ]
        for t in transactions
    ], widths)
    print(f"\n{len(transactions)} transaction(s)")


# --- Reports ---

def cmd_report(args):
    report_type = args.report_type

    if report_type == "summary":
        summary = db.get_inventory_summary()
        print(f"\n{'='*40}")
        print("  INVENTORY SUMMARY")
        print(f"{'='*40}")
        print(f"  Total Products    : {summary['total_products']}")
        print(f"  Total Units       : {summary['total_units'] or 0:,}")
        print(f"  Total Value       : {_fmt_currency(summary['total_value'] or 0)}")
        print(f"  Low Stock Items   : {summary['low_stock_count']}")
        print(f"  Out of Stock      : {summary['out_of_stock_count']}")
        print()

    elif report_type == "categories":
        rows = db.get_category_summary()
        if not rows:
            print("No data.")
            return
        headers = ["Category", "Products", "Total Units", "Total Value"]
        widths = [20, 10, 12, 15]
        print()
        _print_table(headers, [
            [r["category"], r["product_count"], f"{r['total_units']:,}",
             _fmt_currency(r["total_value"] or 0)]
            for r in rows
        ], widths)
        print()

    elif report_type == "low-stock":
        products = db.list_products(low_stock_only=True)
        if not products:
            print("No low-stock products.")
            return
        headers = ["SKU", "Name", "On Hand", "Reorder At", "Need to Order"]
        widths = [12, 30, 10, 12, 14]
        print()
        _print_table(headers, [
            [p.sku, p.name, p.quantity_on_hand, p.reorder_level,
             max(0, p.reorder_quantity - p.quantity_on_hand)]
            for p in products
        ], widths)
        print(f"\n{len(products)} item(s) need restocking")

    elif report_type == "valuation":
        products = db.list_products()
        if not products:
            print("No products.")
            return
        headers = ["SKU", "Name", "Qty", "Cost Price", "Stock Value"]
        widths = [12, 30, 8, 12, 14]
        total = sum(p.stock_value for p in products)
        print()
        _print_table(headers, [
            [p.sku, p.name, p.quantity_on_hand,
             _fmt_currency(p.cost_price), _fmt_currency(p.stock_value)]
            for p in products
        ], widths)
        print(f"\n  Total Inventory Value: {_fmt_currency(total)}")
        print()


# --- Utilities ---

def _resolve_product(identifier: str):
    """Find product by ID or SKU."""
    if identifier.isdigit():
        product = db.get_product_by_id(int(identifier))
    else:
        product = db.get_product_by_sku(identifier.upper())
    if not product:
        print(f"Error: product '{identifier}' not found.")
        sys.exit(1)
    return product


# --- Argument parser ---

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inventory",
        description="Inventory Control System",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    # --- add ---
    p_add = sub.add_parser("add", help="Add a new product")
    p_add.add_argument("sku", help="Unique SKU")
    p_add.add_argument("name", help="Product name")
    p_add.add_argument("--description", "-d", default="")
    p_add.add_argument("--category", "-c", default="General")
    p_add.add_argument("--unit-price", type=float, default=0.0)
    p_add.add_argument("--cost-price", type=float, default=0.0)
    p_add.add_argument("--quantity", "-q", type=int, default=0)
    p_add.add_argument("--reorder-level", type=int, default=10)
    p_add.add_argument("--reorder-quantity", type=int, default=50)
    p_add.add_argument("--unit", default="units")

    # --- update ---
    p_upd = sub.add_parser("update", help="Update product details")
    p_upd.add_argument("product", help="Product ID or SKU")
    p_upd.add_argument("--name")
    p_upd.add_argument("--description")
    p_upd.add_argument("--category")
    p_upd.add_argument("--unit-price", type=float)
    p_upd.add_argument("--cost-price", type=float)
    p_upd.add_argument("--reorder-level", type=int)
    p_upd.add_argument("--reorder-quantity", type=int)
    p_upd.add_argument("--unit")

    # --- delete ---
    p_del = sub.add_parser("delete", help="Delete a product")
    p_del.add_argument("product", help="Product ID or SKU")
    p_del.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")

    # --- show ---
    p_show = sub.add_parser("show", help="Show product details")
    p_show.add_argument("product", help="Product ID or SKU")

    # --- list ---
    p_list = sub.add_parser("list", help="List products")
    p_list.add_argument("--category", "-c")
    p_list.add_argument("--low-stock", action="store_true", help="Show only low-stock items")

    # --- receive ---
    p_recv = sub.add_parser("receive", help="Receive stock (purchase)")
    p_recv.add_argument("product", help="Product ID or SKU")
    p_recv.add_argument("quantity", type=int)
    p_recv.add_argument("--price", type=float, help="Override cost price")
    p_recv.add_argument("--reference", "-r")
    p_recv.add_argument("--notes", "-n")

    # --- sell ---
    p_sell = sub.add_parser("sell", help="Record a sale")
    p_sell.add_argument("product", help="Product ID or SKU")
    p_sell.add_argument("quantity", type=int)
    p_sell.add_argument("--price", type=float, help="Override unit price")
    p_sell.add_argument("--reference", "-r")
    p_sell.add_argument("--notes", "-n")

    # --- adjust ---
    p_adj = sub.add_parser("adjust", help="Set stock to exact quantity (stock-take)")
    p_adj.add_argument("product", help="Product ID or SKU")
    p_adj.add_argument("quantity", type=int, help="New on-hand quantity")
    p_adj.add_argument("--reference", "-r")
    p_adj.add_argument("--notes", "-n")

    # --- return ---
    p_ret = sub.add_parser("return", help="Record a customer return")
    p_ret.add_argument("product", help="Product ID or SKU")
    p_ret.add_argument("quantity", type=int)
    p_ret.add_argument("--price", type=float)
    p_ret.add_argument("--reference", "-r")
    p_ret.add_argument("--notes", "-n")

    # --- history ---
    p_hist = sub.add_parser("history", help="View transaction history")
    p_hist.add_argument("--product", help="Filter by product ID or SKU")
    p_hist.add_argument("--type", choices=[t.value for t in TransactionType],
                        help="Filter by transaction type")
    p_hist.add_argument("--limit", type=int, default=50)

    # --- report ---
    p_rep = sub.add_parser("report", help="Generate reports")
    p_rep.add_argument("report_type",
                       choices=["summary", "categories", "low-stock", "valuation"],
                       metavar="TYPE",
                       help="Report type: summary | categories | low-stock | valuation")

    return parser


def main():
    db.init_db()
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "add": cmd_add,
        "update": cmd_update,
        "delete": cmd_delete,
        "show": cmd_show,
        "list": cmd_list,
        "receive": cmd_receive,
        "sell": cmd_sell,
        "adjust": cmd_adjust,
        "return": cmd_return,
        "history": cmd_history,
        "report": cmd_report,
    }

    if args.command not in commands:
        parser.print_help()
        sys.exit(0)

    commands[args.command](args)


if __name__ == "__main__":
    main()
