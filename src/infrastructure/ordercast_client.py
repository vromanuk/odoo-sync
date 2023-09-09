import functools
from http import HTTPStatus
from typing import Annotated

import requests
import structlog
from fastapi import Depends

from src.api import (
    CreateShippingAddressRequest,
    OrdercastApiValidationException,
    OrdercastApiServerException,
    BulkSignUpByErpIdRequest,
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

    def get_user_by_email(self, email: str):
        return f"{email}hello@gmail.com"

    @error_handler
    def bulk_sign_up_by_erp_id(self, request: BulkSignUpByErpIdRequest):
        response = requests.post(
            url=f"{self.base_url}/merchant/signup-erp-id/",
            data=request.model_dump(),
            headers=self._auth_headers,
        )
        return response

    def get_merchant(self, email):
        pass

    def upsert_user(self, email, defaults):
        pass

    def create_user_profile(self, user_id, defaults):
        pass

    @error_handler
    def create_shipping_address(self, request: CreateShippingAddressRequest):
        response = requests.post(
            url=f"{self.base_url}/merchant/{request.merchant_id}/address/shipping/",
            data=request.model_dump(),
            headers=self._auth_headers,
        )
        return response

    def create_billing_info(self, enterprise_name, address_id, vat):
        pass

    def create_billing(self, name, user_id, billing_info_id):
        pass


# @lru_cache()
def get_ordercast_api(
    settings: Annotated[Settings, Depends(get_settings)]
) -> OrdercastApi:
    return OrdercastApi(settings.ORDERCAST)
