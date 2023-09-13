import functools
from http import HTTPStatus
from typing_extensions import Annotated

import httpx
import structlog
from fastapi import Depends

from src.api import (
    BulkSignUpRequest,
    CreateShippingAddressRequest,
    ListBillingAddressesRequest,
    ListShippingAddressesRequest,
    CreateOrderRequest,
)
from src.api import (
    OrdercastApiValidationException,
    OrdercastApiServerException,
)
from src.config import OrdercastConfig, Settings, get_settings

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
        self._auth_headers = {"Authorization": f"Bearer {self._token}"}

    @error_handler
    def bulk_sign_up(self, request: BulkSignUpRequest):
        return httpx.post(
            url=f"{self.base_url}/merchant/signup/",
            data=request.model_dump(),
            headers=self._auth_headers,
        )

    def get_merchant(self, email):
        pass

    def upsert_user(self, email, defaults):
        pass

    def create_user_profile(self, user_id, defaults):
        pass

    @error_handler
    def create_shipping_address(self, request: CreateShippingAddressRequest):
        return httpx.post(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/shipping/",
            data=request.model_dump(),
            headers=self._auth_headers,
        )

    def create_billing_info(self, enterprise_name, address_id, vat):
        pass

    def create_billing(self, name, user_id, billing_info_id):
        pass

    @error_handler
    def list_billing_addresses(self, request: ListBillingAddressesRequest):
        return httpx.get(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/billing/",
            headers=self._auth_headers,
        )

    @error_handler
    def list_shipping_addresses(self, request: ListShippingAddressesRequest):
        return httpx.get(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/shipping/",
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_categories(self, categories: list) -> None:
        httpx.post(
            url=f"{self.base_url}/category/",
            data=categories,
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_attributes(self, attributes) -> None:
        httpx.post(
            url=f"{self.base_url}/attribute/",
            data=attributes,
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_units(self, units: list) -> None:
        httpx.post(
            url=f"{self.base_url}/product/unit/",
            data=units,
            headers=self._auth_headers,
        )

    @error_handler
    def upsert_products(self, products: list) -> None:
        httpx.post(
            url=f"{self.base_url}/product/",
            data=products,
            headers=self._auth_headers,
        )

    @error_handler
    def get_orders(self, order_ids, from_date):
        # TODO: introduce parameter passing
        return httpx.get(
            url=f"{self.base_url}/order/",
            headers=self._auth_headers,
        )

    @error_handler
    def create_order(self, request: CreateOrderRequest) -> None:
        httpx.post(
            url=f"{self.base_url}/order/?order_status_enum={request.order_status_enum}",
            data=request.model_dump(),
            headers=self._auth_headers,
        )


# @lru_cache()
def get_ordercast_api(
    settings: Annotated[Settings, Depends(get_settings)]
) -> OrdercastApi:
    return OrdercastApi(settings.ORDERCAST)
