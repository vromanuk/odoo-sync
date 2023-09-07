from src.infrastructure import OdooClient
from .models import Partner
from .enums import PartnerType, PartnerAddressType


class OdooProvider:
    def __init__(self, client: OdooClient):
        self._client = client

    def receive_partner_users(self, exclude_user_ids=None):
        users = self.receive_partners(
            exclude_user_ids=exclude_user_ids, partner_type=PartnerType.USER
        )

        if users:
            result = []
            addresses = self.receive_partners(
                parent_ids=[u["id"] for u in users], partner_type=PartnerType.ADDRESS
            )
            for user in users:
                # user_dto = {'id': user['id'], 'name': user['name'], 'email': user['email']}

                billing_addresses = []
                shipping_addresses = []
                if addresses:
                    for address in addresses:
                        if address["parent_id"] == user["id"]:
                            if address["type"] == PartnerAddressType.INVOICE.value:
                                billing_addresses.append(address)
                            elif address["type"] == PartnerAddressType.DELIVERY.value:
                                shipping_addresses.append(address)
                user["billing_addresses"] = billing_addresses
                user["shipping_addresses"] = shipping_addresses
                result.append(user)

            return result

    def receive_partners(
        self, exclude_user_ids=None, parent_ids=None, partner_type=None
    ):
        api_filter_criteria = [
            ("is_company", "=", False),
            ("active", "in", [True, False]),
        ]
        if exclude_user_ids:
            api_filter_criteria.append(("id", "not in", exclude_user_ids))
        if parent_ids:
            api_filter_criteria.append(("parent_id", "in", parent_ids))
        if partner_type:
            if partner_type == PartnerType.USER:
                api_filter_criteria.extend(
                    [
                        ("name", "!=", False),
                        ("email", "!=", False),
                        ("parent_id", "=", False),
                    ]
                )
            elif partner_type == PartnerType.ADDRESS:
                api_filter_criteria.extend(
                    [
                        ("name", "!=", False),
                        ("parent_id", "!=", False),
                        (
                            "type",
                            "in",
                            [
                                PartnerAddressType.INVOICE.value,
                                PartnerAddressType.DELIVERY.value,
                            ],
                        ),
                    ]
                )

        partners = self._client.get_objects("res.partner", criteria=api_filter_criteria)
        remote_supported_langs = self._client.get_objects("res.lang")

        return [
            Partner.build_from(
                odoo_client=self._client,
                partner=partner,
                remote_supported_langs=remote_supported_langs,
            )
            for partner in partners
        ]
