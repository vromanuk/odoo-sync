from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, PositiveInt, EmailStr


class OrdercastCommon(BaseModel):
    id: PositiveInt
    name: str


class OrdercastProduct(OrdercastCommon):
    sku: str


class OrdercastAttribute(OrdercastCommon):
    code: str


class OrdercastCategory(OrdercastCommon):
    code: str


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


class OrdercastMerchant(BaseModel):
    id: PositiveInt
    erp_id: str
    status: OrdercastMerchantStatus
    is_payment_required: bool
    corporate_status_name: str
    sector_id: PositiveInt
    created_at: datetime
    price_rate_id: int
    external_id: str = ""
    info: str = ""
    name: str = ""
    phone: str = ""
    vat: str = ""
    website: str = ""
    note: str = ""
    prices_pdf: Optional[dict[str, Any]] = None
    price_rate: Optional[dict[str, Any]] = None
    catalogs: list[OrdercastMerchantCatalog] = []


class OrdercastFlatMerchant(OrdercastCommon):
    erp_id: str = ""
    billing_addresses: list[dict[str, Any]] = []
    shipping_addresses: list[dict[str, Any]] = []


class OrdercastFlatOrder(BaseModel):
    id: PositiveInt
    created_at: datetime
    created_by: OrdercastUser
    external_id: str
    status: OrdercastOrderStatus
    delivery_method: Optional[OrdercastDeliveryMethod] = None
    shipping_address: Optional[OrdercastShippingAddress] = None
    pickup_location: Optional[OrdercastPickupLocation] = None


class OrdercastOrder(BaseModel):
    id: PositiveInt
    created_at: datetime
    ordered_at: datetime
    external_id: str
    internal_id: int
    note: str
    total_price_gross: int
    total_price_net: int
    tracking_codes: list[str]
    updated_at: datetime
    is_editable: bool
    is_same_address: bool
    lines_amount: int
    taxes: int
    created_by: OrdercastUser
    merchant: OrdercastMerchant
    status: OrdercastOrderStatus
    payments: list[OrdercastPayment]
    price_rate: dict[str, Any]
    company_note: str = ""
    invoice: Optional[dict[str, Any]] = None
    unit_labels: Optional[dict[str, Any]] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[int] = None
    delivery_method: Optional[OrdercastDeliveryMethod] = None
    shipping_address: Optional[OrdercastShippingAddress] = None
    pickup_location: Optional[OrdercastPickupLocation] = None
    billing_address: Optional[OrdercastBillingAddress] = None


class OrdercastAttributeValue(OrdercastCommon):
    pass
