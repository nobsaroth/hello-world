#!/usr/bin/env python3
"""Seed the database with sample data for demonstration."""

import database as db
from models import TransactionType

db.init_db()

products = [
    ("LAPTOP-001", "Laptop Pro 15", "15-inch business laptop", "Electronics",
     1299.99, 850.00, 45, 10, 20, "units"),
    ("LAPTOP-002", "Laptop Air 13", "13-inch ultrabook", "Electronics",
     999.99, 650.00, 8, 10, 15, "units"),
    ("MOUSE-001", "Wireless Mouse", "Ergonomic wireless mouse", "Accessories",
     49.99, 18.00, 120, 25, 100, "units"),
    ("KB-001", "Mechanical Keyboard", "TKL mechanical keyboard", "Accessories",
     129.99, 55.00, 60, 15, 50, "units"),
    ("MONITOR-001", "27\" 4K Monitor", "27-inch 4K IPS display", "Electronics",
     699.99, 420.00, 22, 5, 10, "units"),
    ("CABLE-USB-C", "USB-C Cable 2m", "USB-C to USB-C 2m cable", "Accessories",
     19.99, 4.50, 5, 20, 100, "units"),
    ("HDMI-2M", "HDMI Cable 2m", "HDMI 2.0 cable 2m", "Accessories",
     14.99, 3.00, 200, 30, 150, "units"),
    ("DESK-MAT-L", "Desk Mat Large", "Large leather desk mat", "Furniture",
     79.99, 28.00, 35, 10, 30, "units"),
    ("CHAIR-ERGO", "Ergonomic Chair", "Lumbar support office chair", "Furniture",
     549.99, 280.00, 3, 5, 10, "units"),
    ("SSD-1TB", "SSD 1TB NVMe", "1TB NVMe M.2 SSD", "Storage",
     129.99, 70.00, 0, 10, 30, "units"),
]

created = []
for args in products:
    existing = db.get_product_by_sku(args[0])
    if existing:
        created.append(existing)
    else:
        p = db.create_product(*args)
        created.append(p)
        print(f"  Created: {p.sku} - {p.name}")

# Record some transactions
txns = [
    (0, TransactionType.PURCHASE.value, 50, 850.00, "PO-2024-001"),
    (0, TransactionType.SALE.value, 5, 1299.99, "SO-2024-001"),
    (2, TransactionType.SALE.value, 20, 49.99, "SO-2024-002"),
    (3, TransactionType.SALE.value, 10, 129.99, "SO-2024-003"),
    (4, TransactionType.PURCHASE.value, 10, 420.00, "PO-2024-002"),
    (4, TransactionType.SALE.value, 8, 699.99, "SO-2024-004"),
    (9, TransactionType.PURCHASE.value, 30, 70.00, "PO-2024-003"),
    (9, TransactionType.SALE.value, 30, 129.99, "SO-2024-005"),
]

for prod_idx, txn_type, qty, price, ref in txns:
    p = created[prod_idx]
    db.record_transaction(p.id, txn_type, qty, price, reference=ref)

print("\nSeed data loaded. Run: python inventory.py report summary")
