from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, PositiveInt, model_serializer, EmailStr


class ImageObject(BaseModel):
    filename: str
    key: str
    url: str


class I18Name(BaseModel):
    names: dict[str, str]

    @model_serializer
    def ser_model(self) -> dict[str, str]:
        return {k: v for k, v in self.names.items()}


class PriceRate(BaseModel):
    price: int
    price_rate_id: PositiveInt
    quantity: PositiveInt


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


class Employee(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone: str
    password: str
    language: str


class BulkSignUpRequest(BaseModel):
    employee: Employee
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


class BasePaginatedRequest(BaseModel):
    pageIndex: PositiveInt = 0
    pageSize: PositiveInt = 50
    prevId: PositiveInt = 0


class ListMerchantsRequest(BasePaginatedRequest):
    pass


class ListProductsRequest(BasePaginatedRequest):
    pass


class ListOrdersRequest(BasePaginatedRequest):
    statuses: list[PositiveInt]
    order_ids: Optional[list[int]] = None
    from_date: Optional[datetime] = None


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
    image: Optional[ImageObject] = {}
    name: dict[str, str]
    sku: str
    catalogs: list[dict[str, PositiveInt]]
    categories: list[dict[str, PositiveInt]]


class UpsertCategoriesRequest(BaseModel):
    name: dict[str, str]
    parent_id: Optional[PositiveInt] = None
    parent_code: Optional[str]
    index: PositiveInt
    image: Optional[ImageObject] = {}
    code: str = ""


class UpsertAttributesRequest(BaseModel):
    code: str
    name: str
    index: int = 1
    input_type: int = 1
    is_filter: bool = True
    is_quick_search: bool = True


class UpsertUnitsRequest(BaseModel):
    code: str
    name: I18Name


class UpsertProductVariantsRequest(BaseModel):
    name: I18Name
    barcode: dict[str, str]
    product_id: PositiveInt
    sku: str
    price_rates: list[dict[str, int]]
    unit_code: str
    attribute_values: list[dict[str, Any]]
    place_in_warehouse: str
    customs_code: str
    letter: str
    status: int = 2
    description: str = ""
    packaging: int = 1
    bundle_min_quantity: int = 0
    bundle_max_quantity: int = 0
    in_stock: int = 0
    is_bundle: bool = False
    is_editable_quantity: bool = True
    is_visible_price_net: bool = True
    images: Optional[list[ImageObject]] = []


class UpsertPriceRatesRequest(BaseModel):
    name: str
    show_recommended: bool = False


class AddDeliveryMethodRequest(BaseModel):
    name: I18Name
    is_enabled: bool = True
    minimum_amount: int = 0
    tracking_url: str = "https://www.delivery.com/track?&tracknum="
    is_payment_required: bool = False
    is_tracking_code_generator_enabled: bool = False
    ignore_is_merchant_payment_required: bool = False
    allows_skip_order_processed_on_complete: bool = False
    should_attach_preparation_voucher: bool = False
    is_pickup: bool = False
    is_myself: bool = False


class CreatePickupLocationRequest(BaseModel):
    name: I18Name
    street: str = "Smith Ave"
    city: str = "Bradford"
    postcode: str = "21701"
    country: str = "UNITED_KINGDOM"
    contact_name: str = "John Doe"
    contact_phone: str = "+3281000000"
    image: ImageObject = {}
