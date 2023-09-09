import json
from datetime import datetime
from typing import Optional, Self

from pydantic import BaseModel, PositiveInt

from .enums import CategoryType, OrderStatus, InvoiceStatus


class OdooProductGroup(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    product_group: PositiveInt


class OdooCategory(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    category: PositiveInt
    category_type: CategoryType


class OdooProduct(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    product: PositiveInt


class OdooAttribute(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    attribute: PositiveInt


class OdooOrder(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    order: PositiveInt
    odoo_order_status: OrderStatus
    odoo_invoice_status: InvoiceStatus


class OdooUser(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: Optional[datetime] = None
    user: PositiveInt

    @classmethod
    def from_json(cls, user_json: str) -> Self:
        return cls(**json.loads(user_json))


class OdooDeliveryOption(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    delivery_option: PositiveInt


class OdooWarehouse(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    warehouse: PositiveInt


class OdooAddress(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    address: PositiveInt
    original_address_id: PositiveInt

    @classmethod
    def from_json(cls, user_json: str) -> Self:
        return cls(**json.loads(user_json))


class OdooBasketProduct(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    basket_product: PositiveInt
