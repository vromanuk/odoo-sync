import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, PositiveInt, EmailStr

from .enums import CategoryType, OrderStatus, InvoiceStatus


class OdooCommons(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)
    sync_date: Optional[datetime] = None


class OdooProduct(OdooCommons):
    name: str
    product: Optional[PositiveInt] = None


class OdooCategory(OdooCommons):
    name: str
    category_type: CategoryType
    category: Optional[PositiveInt] = None


class OdooProductVariant(OdooCommons):
    name: str
    product_variant: Optional[PositiveInt] = None


class OdooAttribute(OdooCommons):
    name: str
    attribute: Optional[PositiveInt] = None


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
    name: str
    delivery_option: Optional[PositiveInt] = None


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


class OdooPriceRate(BaseModel):
    id: PositiveInt
    name: str
