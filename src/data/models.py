import json
from datetime import datetime, timezone
from typing import Optional, Any

from pydantic import BaseModel, PositiveInt

from .enums import CategoryType, OrderStatus, InvoiceStatus


class OdooCommons(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)
    sync_date: Optional[datetime] = None

    @classmethod
    def from_json(cls, user_json: str) -> Any:
        return cls(**json.loads(user_json))


class OdooProduct(OdooCommons):
    name: str
    product: Optional[PositiveInt] = None


class OdooCategory(OdooCommons):
    name: str
    category_type: CategoryType
    category: PositiveInt


class OdooProductVariant(OdooCommons):
    name: str
    product_variant: Optional[PositiveInt] = None


class OdooAttribute(OdooCommons):
    name: str
    attribute: PositiveInt


class OdooOrder(OdooCommons):
    order: PositiveInt
    odoo_order_status: OrderStatus
    odoo_invoice_status: InvoiceStatus


class OdooUser(OdooCommons):
    email: str = ""
    street: str = ""
    city: str = ""
    postcode: str = ""
    country: str = ""
    contact_name: str = ""
    contact_phone: str = ""
    ordercast_user: Optional[PositiveInt] = None


class OdooDeliveryOption(OdooCommons):
    name: str
    delivery_option: Optional[PositiveInt] = None


class OdooPickupLocation(OdooCommons):
    name: str
    warehouse: Optional[PositiveInt] = None


class OdooAddress(OdooCommons):
    address: PositiveInt
    original_address_id: Optional[PositiveInt] = None


class OdooBasketProduct(OdooCommons):
    basket_product: PositiveInt


class OdooPriceRate(BaseModel):
    id: PositiveInt
    name: str


class OdooAttributeValue(OdooCommons):
    name: str
    ordercast_id: PositiveInt
