import functools
from http import HTTPStatus
from typing import Annotated

import requests
import structlog
from fastapi import Depends

from src.api import (
    OrdercastApiValidationException,
    OrdercastApiServerException,
)
from src.api import (
    BulkSignUpByErpIdRequest,
    CreateShippingAddressRequest,
    ListBillingAddressesRequest,
    ListShippingAddressesRequest,
)
from src.config import OrdercastConfig, Settings, get_settings

logger = structlog.getLogger(__name__)


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
            if response.status_code not in [HTTPStatus.OK, HTTPStatus.CREATED]:
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
    def bulk_sign_up_by_erp_id(self, request: BulkSignUpByErpIdRequest):
        return requests.post(
            url=f"{self.base_url}/merchant/signup-erp-id/",
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
        return requests.post(
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
        return requests.get(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/billing/",
            headers=self._auth_headers,
        )

    def list_shipping_addresses(self, request: ListShippingAddressesRequest):
        return requests.get(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/shipping/",
            headers=self._auth_headers,
        )


# @lru_cache()
def get_ordercast_api(
    settings: Annotated[Settings, Depends(get_settings)]
) -> OrdercastApi:
    return OrdercastApi(settings.ORDERCAST)
