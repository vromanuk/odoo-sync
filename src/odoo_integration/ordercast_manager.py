from typing import Annotated, Any, Optional

from fastapi import Depends

from src.api import (
    CreateShippingAddressRequest,
    ListBillingAddressesRequest,
    ListShippingAddressesRequest,
)
from src.infrastructure import OrdercastApi, get_ordercast_api
from .helpers import is_not_empty, is_empty
from .odoo_repo import OdooRepo


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

    def get_billing_addresses(self, merchant_id: int):
        return self.ordercast_api.list_billing_addresses(
            ListBillingAddressesRequest(merchant_id=merchant_id)
        )

    def get_shipping_addresses(self, merchant_id: int):
        return self.ordercast_api.list_shipping_addresses(
            ListShippingAddressesRequest(merchant_id=merchant_id)
        )

    def get_users(self, odoo_repo: OdooRepo):
        # users = User.objects.all()
        users = self.ordercast_api.get_all_merchants()
        users_to_create = []
        for user in users:
            user_dto = {"id": user.id, "name": user.name}

            # user_remote = UserExternal.objects.filter(user_id=user.id).first()
            user_remote = odoo_repo.get_user(user.id)
            if user_remote:
                user_dto["_remote_id"] = user_remote.odoo_id
            # if user.erp_id:
            #     user_dto["erp_id"] = user.erp_id
            if user.profile:
                user_dto["language"] = user.profile.language
                if user.profile.website:
                    user_dto["website"] = user.profile.website
                if user.profile.signup_info:
                    user_dto["comment"] = user.profile.signup_info

            user_dto["name"] = user.name
            user_dto["email"] = user.email
            # user_dto['approved'] = user.is_approved
            # user_dto['activated'] = user.is_active
            # billing_addresses = Billing.objects.filter(user_id=user.id).all()
            billing_addresses = self.get_billing_addresses(user.id)
            billing_address_dtos = []
            if billing_addresses and billing_addresses.count() > 0:
                for billing_address in billing_addresses:
                    if billing_address.billing_info:
                        billing_address_dto = self.get_address(
                            billing_address.billing_info.address
                        )
                        billing_address_dto[
                            "name"
                        ] = billing_address.billing_info.enterprise_name
                        billing_address_dto["vat"] = billing_address.billing_info.vat
                        if is_not_empty(user_dto, "website"):
                            billing_address_dto["website"] = user_dto["website"]
                        # if is_not_empty(user_dto, 'email'):
                        #     billing_address_dto['email'] = user_dto['email']
                        if is_not_empty(user_dto, "language"):
                            billing_address_dto["language"] = user_dto["language"]
                        if is_not_empty(user_dto, "signup_info"):
                            billing_address_dto["comment"] = user_dto["signup_info"]
                        if is_not_empty(user_dto, "_remote_id"):
                            if (
                                is_empty(billing_address_dto, "_remote_id")
                                or billing_address_dto["_remote_id"]
                                != user_dto["_remote_id"]
                            ):
                                billing_address_dto["parent_id"] = user_dto[
                                    "_remote_id"
                                ]
                        billing_address_dtos.append(billing_address_dto)

                user_dto["billing_addresses"] = billing_address_dtos

            # shipping_addresses = ShippingAddress.objects.filter(user_id=user.id).all()
            shipping_addresses = self.get_shipping_addresses(user.id)
            shipping_address_dtos = []
            if shipping_addresses and shipping_addresses.count() > 0:
                for shipping_address in shipping_addresses:
                    if shipping_address.address:
                        shipping_address_dto = self.get_address(
                            shipping_address.address, odoo_repo=odoo_repo
                        )
                        # shipping_address_dto['name'] = shipping_address.name
                        if is_not_empty(user_dto, "website"):
                            shipping_address_dto["website"] = user_dto["website"]
                        # shipping_address_dto['email'] = user_dto['email']
                        if is_not_empty(user_dto, "language"):
                            shipping_address_dto["language"] = user_dto["language"]
                        if is_not_empty(user_dto, "signup_info"):
                            shipping_address_dto["comment"] = user_dto["signup_info"]
                        if is_not_empty(user_dto, "_remote_id"):
                            if (
                                is_empty(shipping_address_dto, "_remote_id")
                                or shipping_address_dto["_remote_id"]
                                != user_dto["_remote_id"]
                            ):
                                shipping_address_dto["parent_id"] = user_dto[
                                    "_remote_id"
                                ]

                        shipping_address_dtos.append(shipping_address_dto)

                user_dto["shipping_addresses"] = shipping_address_dtos
            users_to_create.append(user_dto)

        return users_to_create

    def get_address(self, address, odoo_repo: OdooRepo):
        if address:
            address_dto = {
                "id": address.id,
                "name": address.name,
                "address_one": address.address_one,
                "postal_code": address.code,
                "phone": address.phone,
                "email": address.email,
            }
            if address.address_two:
                address_dto["address_two"] = address.address_two
            if address.city:
                address_dto["city"] = address.city.name
                if address.city.region:
                    address_dto["region"] = address.city.region.name
            if address.country:
                address_dto["country"] = address.country.name
            if address.copy_from:
                address_id = address.copy_from.id
            else:
                address_id = address.id
            # external_address = AddressExternal.objects.filter(
            #     address_id=address_id
            # ).first()
            external_address = odoo_repo.get_address(address_id)
            if external_address:
                address_dto["_remote_id"] = external_address.odoo_id
            return address_dto


# @lru_cache()
def get_ordercast_manager(
    ordercast_api: Annotated[OrdercastApi, Depends(get_ordercast_api)]
) -> OrdercastManager:
    return OrdercastManager(ordercast_api)
