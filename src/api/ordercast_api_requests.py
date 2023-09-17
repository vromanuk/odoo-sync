from typing import Optional

from pydantic import BaseModel, PositiveInt


class ImageObject(BaseModel):
    filename: str
    key: str
    url: str


class Merchant(BaseModel):
    erp_id: PositiveInt
    name: str
    phone: str
    city: str
    sector_id: PositiveInt
    postcode: str
    street: str
    vat: str = ""
    website: str = ""
    info: str = ""
    corporate_status_id: int = 1
    country_alpha_2: str = "GB"


class BulkSignUpRequest(BaseModel):
    merchant: Merchant


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


class ListMerchantsRequest(BaseModel):
    pageIndex: PositiveInt = 0
    pageSize: PositiveInt = 50
    prevId: PositiveInt = 0


class CreateOrderRequest(BaseModel):
    order_status_enum: PositiveInt
    merchant_id: PositiveInt
    price_rate_id: PositiveInt
    external_id: PositiveInt

    class Config:
        exclude = {"order_status_enum"}


class UpdateSettingsRequest(BaseModel):
    url: Optional[str] = ""
    extra_phone: Optional[str] = ""
    fax: Optional[str] = ""
    payment_info: Optional[str] = ""


class CreateBillingAddressRequest(BaseModel):
    merchant_id: PositiveInt
    name: str
    street: str
    city: str
    postcode: str
    country: str
    contact_name: Optional[str] = ""
    contact_phone: Optional[str] = ""
    corporate_status_name: Optional[str] = ""
    vat: Optional[str] = ""

    class Config:
        exclude = {"merchant_id"}


class UpsertProductsRequest(BaseModel):
    image: Optional[ImageObject] = None
    name: str
    sku: str
    catalogs: list[PositiveInt]
    categories: list[PositiveInt]


class UpsertCategoriesRequest(BaseModel):
    name: str
    parent_id: Optional[PositiveInt]
    parent_code: str
    index: PositiveInt
    image: Optional[ImageObject] = None
    code: str = ""


class UpsertAttributesRequest(BaseModel):
    code: str
    name: str
    index: int = 1
    input_type: int = 1
    is_filter: bool = True
    is_quick_search: bool = True
