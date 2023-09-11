from typing import Optional

from pydantic import BaseModel, PositiveInt


class BulkSignUpByErpIdRequest(BaseModel):
    erp_id: PositiveInt


class CreateShippingAddressRequest(BaseModel):
    merchant_id: PositiveInt
    name: str
    street: str
    city: str
    postcode: str
    country: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None

    class Config:
        exclude = {"merchant_id"}


class ListBillingAddressesRequest(BaseModel):
    merchant_id: PositiveInt


class ListShippingAddressesRequest(BaseModel):
    merchant_id: PositiveInt


class CreateOrderRequest(BaseModel):
    order_status_enum: PositiveInt
    merchant_id: PositiveInt
    price_rate_id: PositiveInt
    external_id: PositiveInt

    class Config:
        exclude = {"order_status_enum"}
