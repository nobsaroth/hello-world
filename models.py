from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TransactionType(Enum):
    PURCHASE = "purchase"
    SALE = "sale"
    ADJUSTMENT = "adjustment"
    RETURN = "return"


@dataclass
class Product:
    id: int
    sku: str
    name: str
    description: str
    category: str
    unit_price: float
    cost_price: float
    quantity_on_hand: int
    reorder_level: int
    reorder_quantity: int
    unit: str
    created_at: str
    updated_at: str

    @property
    def is_low_stock(self) -> bool:
        return self.quantity_on_hand <= self.reorder_level

    @property
    def stock_value(self) -> float:
        return self.quantity_on_hand * self.cost_price


@dataclass
class Transaction:
    id: int
    product_id: int
    transaction_type: str
    quantity: int
    unit_price: float
    reference: str
    notes: str
    created_at: str
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
