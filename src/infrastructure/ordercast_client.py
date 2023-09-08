from http import HTTPStatus
from typing import Annotated

import requests
from fastapi import Depends

from src.api import CreateShippingAddressRequest, OrdercastApiException
from src.config import OrdercastConfig, Settings, get_settings


class OrdercastApi:
    def __init__(self, config: OrdercastConfig):
        self.BASE_URL = config.BASE_URL

    def get_user_by_email(self, email: str):
        return f"{email}hello@gmail.com"

    def save_users(self, users):
        pass

    def get_merchant(self, email):
        pass

    def upsert_user(self, email, defaults):
        pass

    def create_user_profile(self, user_id, defaults):
        pass

    def create_shipping_address(self, request: CreateShippingAddressRequest):
        response = requests.post(
            url=f"{self.BASE_URL}/merchant/{request.merchant_id}/address/shipping",
            data=request.model_dump(),
        )
        if response.status_code != HTTPStatus.CREATED:
            raise OrdercastApiException(
                f"Request `create_shipping_address` failed => status: {response.status_code}, response: {response.text}"
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
