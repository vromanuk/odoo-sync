from typing import Annotated, Any, Optional

from fastapi import Depends

from src.api import CreateShippingAddressRequest
from src.infrastructure import OrdercastApi, get_ordercast_api


class OrdercastManager:
    def __init__(self, ordercast_api: OrdercastApi) -> None:
        self.ordercast_api = ordercast_api

    def get_user(self, email: str):
        return self.ordercast_api.get_merchant(email)

    def upsert_user(self, email: str, defaults: dict[str, Any]):
        return self.ordercast_api.bulk_signup()

    def create_shipping_address(
        self,
        user_id: int,
        name: str,
        street: str,
        city: str,
        postcode: str,
        country: str,
        contact_name: Optional[str] = None,
        contact_phone: Optional[str] = None,
    ):
        return self.ordercast_api.create_shipping_address(
            CreateShippingAddressRequest(
                merchange_id=user_id,
                name=name,
                street=street,
                city=city,
                postcode=postcode,
                country=country,
                contact_name=contact_name,
                contact_phone=contact_phone,
            )
        )


# @lru_cache()
def get_ordercast_manager(
    ordercast_api: Annotated[OrdercastApi, Depends(get_ordercast_api)]
) -> OrdercastManager:
    return OrdercastManager(ordercast_api)
