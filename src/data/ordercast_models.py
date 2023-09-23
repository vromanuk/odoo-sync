from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, PositiveInt, EmailStr


class OrdercastCommon(BaseModel):
    id: PositiveInt
    name: str


class OrdercastFlatMerchant(OrdercastCommon):
    erp_id: Optional[str]


class OrdercastProduct(OrdercastCommon):
    sku: str


class OrdercastAttribute(OrdercastCommon):
    pass


class OrdercastCategory(OrdercastCommon):
    code: str


class OrdercastFlatOrder(BaseModel):
    id: PositiveInt
    created_at: datetime
    updated_at: datetime


class OrdercastUser(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone: str
    id: PositiveInt
    full_name: str
    is_merchant: bool


class OrdercastMerchantCatalog(BaseModel):
    code: str
    is_default: bool
    is_visible: bool
    name: str
    id: PositiveInt
    is_subscribed: bool


class OrdercastMerchantStatus(BaseModel):
    id: PositiveInt
    color: str
    enum: int
    name: str


class OrdercastMerchant(BaseModel):
    erp_id: str
    external_id: str
    info: str
    name: str
    phone: str
    sector_id: PositiveInt
    vat: str
    website: str
    id: PositiveInt
    created_at: datetime
    price_rate_id: int
    note: str
    is_payment_required: bool
    corporate_status_name: str
    prices_pdf: dict[str, Any]
    price_rate: dict[str, Any]
    catalogs: list[OrdercastMerchantCatalog]
    status: OrdercastMerchantStatus


class OrdercastDeliveryMethod(BaseModel):
    is_enabled: bool
    minimum_amount: int
    name: dict[str, Any]
    tracking_url: str
    is_payment_required: bool
    is_tracking_code_generator_enabled: bool
    ignore_is_merchant_payment_required: bool
    allows_skip_order_processed_on_complete: bool
    should_attach_preparation_voucher: bool
    id: PositiveInt
    created_at: datetime
    is_pickup: bool
    is_myself: bool


class OrdercastShippingAddress(BaseModel):
    id: PositiveInt
    city: str
    city_area: str
    contact_name: str
    contact_phone: str
    country: str
    country_alpha_2: str
    name: str
    postcode: str
    street: str


class OrdercastOrderStatus(BaseModel):
    id: PositiveInt
    name: str
    enum: int


class OrdercastPayment(BaseModel):
    id: PositiveInt
    created_at: datetime
    description: str
    status: OrdercastOrderStatus
    total_price_gross: int
    total_price_net: int
    promo_discount: int
    promo_redeem_by: datetime
    receipt_link: str


class OrdercastPickupLocation(BaseModel):
    id: PositiveInt
    city: str
    city_area: str
    contact_name: str
    contact_phone: str
    country: str
    country_alpha_2: str
    name: str
    postcode: str
    street: str
    image: dict[str, Any]


class OrdercastBillingAddress(BaseModel):
    id: PositiveInt
    city: str
    city_area: str
    contact_name: str
    contact_phone: str
    country: str
    country_alpha_2: str
    name: str
    postcode: str
    street: str
    corporate_status_name: str
    vat: str


class OrdercastOrder(BaseModel):
    id: PositiveInt
    created_at: datetime
    ordered_at: datetime
    completed_at: datetime
    deadline: int
    external_id: str
    internal_id: int
    invoice: dict[str, Any]
    unit_labels: dict[str, Any]
    note: str
    total_price_gross: int
    total_price_net: int
    tracking_codes: list[str]
    updated_at: datetime
    company_note: str
    images_zip: dict[str, Any]
    is_editable: bool
    is_same_address: bool
    lines_amount: int
    taxes: int
    created_by: OrdercastUser
    delivery_method: OrdercastDeliveryMethod
    merchant: OrdercastMerchant
    shipping_address: OrdercastShippingAddress
    status: OrdercastOrderStatus
    payments: list[OrdercastPayment]
    pickup_location: OrdercastPickupLocation
    price_rate: dict[str, Any]
    billing_address: OrdercastBillingAddress
