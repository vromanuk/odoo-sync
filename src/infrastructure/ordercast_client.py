import functools
from http import HTTPStatus
from typing import Annotated

import httpx
import structlog
from fastapi import Depends
from httpx import Response

from src.api import (
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
)
from src.api import (
    OrdercastApiValidationException,
    OrdercastApiServerException,
)
from src.config import OrdercastConfig, Settings, get_settings
from src.data import Locale

logger = structlog.getLogger(__name__)

OK_STATUSES = [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.NO_CONTENT]


def error_handler(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            response = func(self, *args, **kwargs)
            func_name = func.__qualname__
            if response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY:
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
            url=f"{self.base_url}/company/merchant/?pageIndex={request.pageIndex}&pageSize={request.pageSize}&prevId={request.prevId}",
            headers=self._auth_headers,
        )

    @error_handler
    def create_shipping_address(
        self, request: CreateShippingAddressRequest
    ) -> Response:
        return httpx.post(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/shipping/",
            data=request.model_dump(),
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
    def upsert_attributes(self, attributes) -> Response:
        return httpx.post(
            url=f"{self.base_url}/attribute/",
            data=attributes,
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_units(self, units: list) -> Response:
        return httpx.post(
            url=f"{self.base_url}/product/unit/",
            data=units,
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
    def get_orders(self, order_ids, from_date) -> Response:
        # TODO: introduce parameter passing
        return httpx.get(
            url=f"{self.base_url}/order/",
            headers=self._auth_headers,
        )

    @error_handler
    def create_order(self, request: CreateOrderRequest) -> Response:
        return httpx.post(
            url=f"{self.base_url}/order/?order_status_enum={request.order_status_enum}",
            data=request.model_dump(),
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
            data=request.model_dump(),
            headers=self._auth_headers,
        )

    @error_handler
    def create_billing_address(self, request: CreateBillingAddressRequest) -> Response:
        return httpx.post(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/billing",
            data=request.model_dump(),
            headers=self._auth_headers,
        )

    @error_handler
    def list_sectors(self) -> Response:
        return httpx.get(
            url=f"{self.base_url}/sector/",
            headers=self._auth_headers,
        )


# @lru_cache()
def get_ordercast_api(
    settings: Annotated[Settings, Depends(get_settings)]
) -> OrdercastApi:
    return OrdercastApi(settings.ORDERCAST)
