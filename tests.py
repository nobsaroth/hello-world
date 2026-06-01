#!/usr/bin/env python3
"""Unit tests for the Inventory Control System."""

import os
import sys
import unittest
import tempfile

# Use a temp DB for tests
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
import database
database.DB_PATH = _tmp.name

import database as db
from models import Product, Transaction, TransactionType


class TestDatabase(unittest.TestCase):

    def setUp(self):
        db.init_db()

    def _make_product(self, sku="TEST-001", name="Test Product", qty=100):
        return db.create_product(
            sku=sku, name=name, description="desc", category="Test",
            unit_price=10.0, cost_price=5.0,
            quantity_on_hand=qty, reorder_level=10,
            reorder_quantity=50, unit="units"
        )

    def test_create_and_fetch_product(self):
        p = self._make_product()
        self.assertIsNotNone(p.id)
        self.assertEqual(p.sku, "TEST-001")
        fetched = db.get_product_by_id(p.id)
        self.assertEqual(fetched.name, "Test Product")

    def test_get_by_sku(self):
        p = self._make_product(sku="SKU-XYZ")
        found = db.get_product_by_sku("SKU-XYZ")
        self.assertEqual(found.id, p.id)

    def test_duplicate_sku_raises(self):
        self._make_product(sku="DUP-001")
        with self.assertRaises(Exception):
            self._make_product(sku="DUP-001")

    def test_update_product(self):
        p = self._make_product(sku="UPD-001")
        updated = db.update_product(p.id, name="Updated Name", unit_price=20.0)
        self.assertEqual(updated.name, "Updated Name")
        self.assertEqual(updated.unit_price, 20.0)

    def test_delete_product(self):
        p = self._make_product(sku="DEL-001")
        result = db.delete_product(p.id)
        self.assertTrue(result)
        self.assertIsNone(db.get_product_by_id(p.id))

    def test_adjust_stock_positive(self):
        p = self._make_product(sku="STK-001", qty=50)
        updated = db.adjust_stock(p.id, 25)
        self.assertEqual(updated.quantity_on_hand, 75)

    def test_adjust_stock_negative(self):
        p = self._make_product(sku="STK-002", qty=50)
        updated = db.adjust_stock(p.id, -30)
        self.assertEqual(updated.quantity_on_hand, 20)

    def test_low_stock_flag(self):
        p = self._make_product(sku="LOW-001", qty=5)
        self.assertTrue(p.is_low_stock)
        p2 = self._make_product(sku="LOW-002", qty=100)
        self.assertFalse(p2.is_low_stock)

    def test_stock_value(self):
        p = self._make_product(sku="VAL-001", qty=10)
        self.assertAlmostEqual(p.stock_value, 50.0)

    def test_list_products_category_filter(self):
        self._make_product(sku="CAT-001")
        db.create_product("CAT-002", "Other", "", "OtherCat",
                          10.0, 5.0, 100, 10, 50, "units")
        test_products = db.list_products(category="Test")
        categories = {p.category for p in test_products}
        self.assertIn("Test", categories)
        self.assertNotIn("OtherCat", categories)

    def test_list_products_low_stock_filter(self):
        self._make_product(sku="LS-001", qty=5)
        self._make_product(sku="LS-002", qty=100)
        low = db.list_products(low_stock_only=True)
        skus = [p.sku for p in low]
        self.assertIn("LS-001", skus)
        self.assertNotIn("LS-002", skus)

    def test_record_and_list_transaction(self):
        p = self._make_product(sku="TXN-001")
        txn = db.record_transaction(p.id, TransactionType.PURCHASE.value,
                                    20, 5.0, reference="PO-TEST")
        self.assertEqual(txn.quantity, 20)
        self.assertEqual(txn.transaction_type, TransactionType.PURCHASE.value)

        txns = db.list_transactions(product_id=p.id)
        self.assertTrue(any(t.reference == "PO-TEST" for t in txns))

    def test_transaction_type_filter(self):
        p = self._make_product(sku="TXN-002")
        db.record_transaction(p.id, TransactionType.PURCHASE.value, 10, 5.0)
        db.record_transaction(p.id, TransactionType.SALE.value, 5, 10.0)
        purchases = db.list_transactions(product_id=p.id,
                                         transaction_type=TransactionType.PURCHASE.value)
        self.assertTrue(all(t.transaction_type == TransactionType.PURCHASE.value
                            for t in purchases))

    def test_inventory_summary(self):
        self._make_product(sku="SUM-001", qty=10)
        summary = db.get_inventory_summary()
        self.assertIn("total_products", summary)
        self.assertGreater(summary["total_products"], 0)

    def test_category_summary(self):
        self._make_product(sku="CSUM-001")
        rows = db.get_category_summary()
        self.assertTrue(len(rows) > 0)
        self.assertIn("category", rows[0])
        self.assertIn("total_value", rows[0])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        os.unlink(_tmp.name)
