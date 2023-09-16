import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, PositiveInt, EmailStr

from .enums import CategoryType, OrderStatus, InvoiceStatus


class OdooCommons(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)
    sync_date: Optional[datetime]


class OdooProduct(OdooCommons):
    product: PositiveInt


class OdooCategory(OdooCommons):
    category: PositiveInt
    category_type: CategoryType


class OdooProductVariant(OdooCommons):
    product_variant: PositiveInt


class OdooAttribute(OdooCommons):
    attribute: PositiveInt


class OdooOrder(OdooCommons):
    order: PositiveInt
    odoo_order_status: OrderStatus
    odoo_invoice_status: InvoiceStatus


class OdooUser(OdooCommons):
    email: EmailStr
    user: Optional[PositiveInt] = None

    @classmethod
    def from_json(cls, user_json: str) -> "OdooUser":
        return cls(**json.loads(user_json))


class OdooDeliveryOption(OdooCommons):
    delivery_option: PositiveInt


class OdooWarehouse(OdooCommons):
    warehouse: PositiveInt


class OdooAddress(OdooCommons):
    address: PositiveInt
    original_address_id: PositiveInt

    @classmethod
    def from_json(cls, user_json: str) -> "OdooAddress":
        return cls(**json.loads(user_json))


class OdooBasketProduct(OdooCommons):
    basket_product: PositiveInt
