import functools
from http import HTTPStatus
from typing import Annotated, Callable, Any

import httpx
import structlog
import tenacity
from fastapi import Depends
from httpx import Response

from src.config import OrdercastConfig, Settings, get_settings
from src.data import Locale
from .exceptions import (
    OrdercastApiValidationException,
    OrdercastApiServerException,
)
from .ordercast_api_requests import (
    BulkSignUpRequest,
    CreateShippingAddressRequest,
    ListBillingAddressesRequest,
    ListShippingAddressesRequest,
    CreateOrderRequest,
    UpdateSettingsRequest,
    CreateBillingAddressRequest,
    ListMerchantsRequest,
    UpsertProductsRequest,
    UpsertCategoriesRequest,
    UpsertAttributesRequest,
    UpsertProductVariantsRequest,
    UpsertUnitsRequest,
    ListProductsRequest,
    UpsertPriceRatesRequest,
    AddDeliveryMethodRequest,
    CreatePickupLocationRequest,
    ListOrdersRequest,
)

logger = structlog.getLogger(__name__)

OK_STATUSES = {HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.NO_CONTENT}
CLIENT_ERRORS = {
    HTTPStatus.UNPROCESSABLE_ENTITY,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.BAD_REQUEST,
}


def error_handler(func: Callable[..., Response]) -> Callable[..., Response]:
    @functools.wraps(func)
    @tenacity.retry(
        wait=tenacity.wait_random(min=0.5, max=2.0),
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_not_exception_type(OrdercastApiValidationException),
    )
    def wrapper(
        self: "OrdercastApi", *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        try:
            response = func(self, *args, **kwargs)
            func_name = func.__qualname__
            if response.status_code in CLIENT_ERRORS:
                logger.error(
                    f"Validation error for `{func_name}` request => {response.text}"
                )
                raise OrdercastApiValidationException(
                    f"Validation error for `{func_name}` request => {response.text}"
                )
            if response.status_code not in OK_STATUSES:
                logger.error(
                    f"Ordercast server error {response.status_code} {response.text} for `{func_name}`"
                )
                raise OrdercastApiServerException(
                    f"Request `{func_name}` failed => {response.status_code} {response.text}"
                )
            return response
        except Exception as e:
            logger.error(f"Unexpected error {e}")
            raise e

    return wrapper


class OrdercastApi:
    def __init__(self, config: OrdercastConfig):
        self.base_url = config.BASE_URL
        self._token = config.TOKEN
        self._auth_headers = {
            "Authorization": f"Bearer {self._token}",
            "accept": "application/json",
        }

    @error_handler
    def bulk_signup(self, request: list[BulkSignUpRequest]) -> Response:
        return httpx.post(
            url=f"{self.base_url}/merchant/signup/",
            json=[model.model_dump() for model in request],
            headers=self._auth_headers,
        )

    @error_handler
    def get_merchants(self, request: ListMerchantsRequest) -> Response:
        return httpx.get(
            url=f"{self.base_url}/company/merchant/321pageIndex={request.pageIndex}&pageSize={request.pageSize}&prevId={request.prevId}",
            headers=self._auth_headers,
        )

    @error_handler
    def create_shipping_address(
        self, request: CreateShippingAddressRequest
    ) -> Response:
        return httpx.post(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/shipping/",
            json=request.model_dump(),
            headers=self._auth_headers,
        )

    @error_handler
    def list_billing_addresses(self, request: ListBillingAddressesRequest) -> Response:
        return httpx.get(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/billing/",
            headers=self._auth_headers,
        )

    @error_handler
    def list_shipping_addresses(
        self, request: ListShippingAddressesRequest
    ) -> Response:
        return httpx.get(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/shipping/",
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_categories(self, request: list[UpsertCategoriesRequest]) -> Response:
        return httpx.post(
            url=f"{self.base_url}/category/",
            json=[model.model_dump() for model in request],
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_attributes(self, request: list[UpsertAttributesRequest]) -> Response:
        return httpx.post(
            url=f"{self.base_url}/attribute/",
            json=[model.model_dump() for model in request],
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_units(self, request: list[UpsertUnitsRequest]) -> Response:
        return httpx.post(
            url=f"{self.base_url}/product/unit/",
            json=[model.model_dump() for model in request],
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_products(self, request: list[UpsertProductsRequest]) -> Response:
        return httpx.post(
            url=f"{self.base_url}/product/",
            json=[model.model_dump() for model in request],
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_product_variants(
        self, request: list[UpsertProductVariantsRequest]
    ) -> Response:
        return httpx.post(
            url=f"{self.base_url}/product/variant/",
            json=[model.model_dump() for model in request],
            headers=self._auth_headers,
        )

    @error_handler
    def get_orders_for_sync(self, request: ListOrdersRequest) -> Response:
        statuses = "&".join(
            [f"status_ids={status_id}" for status_id in request.statuses]
        )
        return httpx.get(
            url=f"{self.base_url}/order/?pageIndex={request.pageIndex}&pageSize={request.pageSize}&prevId={request.prevId}&{statuses}",
            headers=self._auth_headers,
        )

    @error_handler
    def create_order(self, request: CreateOrderRequest) -> Response:
        return httpx.post(
            url=f"{self.base_url}/order/?order_status_enum={request.order_status_enum}",
            json=request.model_dump(),
            headers=self._auth_headers,
        )

    @error_handler
    def update_default_language(self, locale: Locale) -> Response:
        return httpx.put(
            url=f"{self.base_url}/company/settings/language?={locale}",
            headers=self._auth_headers,
        )

    @error_handler
    def update_settings(self, request: UpdateSettingsRequest) -> Response:
        return httpx.put(
            url=f"{self.base_url}/company/settings/settings",
            json=request.model_dump(),
            headers=self._auth_headers,
        )

    @error_handler
    def create_billing_address(self, request: CreateBillingAddressRequest) -> Response:
        return httpx.post(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/billing",
            json=request.model_dump(),
            headers=self._auth_headers,
        )

    @error_handler
    def list_sectors(self) -> Response:
        return httpx.get(
            url=f"{self.base_url}/sector/",
            headers=self._auth_headers,
        )

    @error_handler
    def list_catalogs(self) -> Response:
        return httpx.get(
            url=f"{self.base_url}/catalog/",
            headers=self._auth_headers,
        )

    @error_handler
    def get_products(self, request: ListProductsRequest) -> Response:
        return httpx.get(
            url=f"{self.base_url}/product/?pageIndex={request.pageIndex}&pageSize={request.pageSize}&prevId={request.prevId}",
            headers=self._auth_headers,
        )

    @error_handler
    def get_attributes(self) -> Response:
        return httpx.get(
            url=f"{self.base_url}/attribute/",
            headers=self._auth_headers,
        )

    @error_handler
    def get_categories(self) -> Response:
        return httpx.get(
            url=f"{self.base_url}/category/",
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_price_rate(self, request: UpsertPriceRatesRequest) -> Response:
        return httpx.post(
            url=f"{self.base_url}/price-rate",
            json=request.model_dump(),
            headers=self._auth_headers,
        )

    @error_handler
    def get_price_rates(self) -> Response:
        return httpx.get(
            url=f"{self.base_url}/price-rate/",
            headers=self._auth_headers,
        )

    @error_handler
    def add_delivery_method(self, request: AddDeliveryMethodRequest) -> Response:
        return httpx.post(
            url=f"{self.base_url}/delivery/",
            json=request.model_dump(),
            headers=self._auth_headers,
        )

    @error_handler
    def add_pickup_location(self, request: CreatePickupLocationRequest) -> Response:
        return httpx.post(
            url=f"{self.base_url}/company/pickup-location/",
            json=request.model_dump(),
            headers=self._auth_headers,
        )

    @error_handler
    def get_order_statuses(self) -> Response:
        return httpx.get(
            url=f"{self.base_url}/order/status/",
            headers=self._auth_headers,
        )

    @error_handler
    def get_order(self, order_id: int) -> Response:
        return httpx.get(
            url=f"{self.base_url}/order/{order_id}/",
            headers=self._auth_headers,
        )


def get_ordercast_api(
    settings: Annotated[Settings, Depends(get_settings)]
) -> OrdercastApi:
    return OrdercastApi(settings.ORDERCAST)
