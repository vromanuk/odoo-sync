import secrets
from datetime import datetime, timezone
from functools import lru_cache
from logging import getLogger
from typing import Annotated

from fastapi import Depends

from src.data import UserStatus, OdooUser, OdooAddress
from .helpers import is_empty, is_not_empty
from .odoo_manager import OdooManager, get_odoo_provider
from .odoo_repo import OdooRepo, get_odoo_repo
from .ordercast_manager import OrdercastManager, get_ordercast_manager
from .validators import validate_partners

logger = getLogger(__name__)


class OdooSyncManager:
    def __init__(
        self,
        repo: OdooRepo,
        odoo_manager: OdooManager,
        ordercast_manager: OrdercastManager,
    ) -> None:
        self.repo = repo
        self.odoo_manager = odoo_manager
        self.ordercast_manager = ordercast_manager

    def sync(self):
        logger.info("Start full syncing with Odoo.")
        self.sync_users()

        # self.logger.info("Start receive products data from Odoo")
        # self.receive_products(products_full_sync)
        #
        # self.logger.info("Start receive order data from Odoo")
        # self.receive_order_data()

        # last_successful_sync_date = None
        #
        # last_successful_sync = ProductSync.objects.filter(type=ProductSync.SYNC_TYPE_ODOO_SYNC,
        #                                                   state=ProductSync.COMPLETED).order_by("updated_at").last()
        # if last_successful_sync:
        #     last_successful_sync_date = last_successful_sync.updated_at
        # last_receive_date = OrderExternal.objects.last_sync_date()
        #
        # self.logger.info("Start sync orders with Odoo")
        # self.send_orders(from_date=last_successful_sync_date)
        # self.receive_orders(from_date=last_receive_date)
        # self.check_deletion()

    def sync_users(self):
        logger.info("Started syncing user's data with Odoo.")
        self.sync_users_from_odoo()
        self.sync_users_to_odoo()

    def sync_users_from_odoo(self):
        users = self.repo.get_users()
        partners = validate_partners(
            self.odoo_manager.receive_partner_users(
                exclude_user_ids=[p.odoo_id for p in users]
            ),
            odoo_repo=self.repo,
            ordercast_manager=self.ordercast_manager,
        )
        logger.info(f"Received partners => {len(partners)}, started saving them.")

        for partner in partners:
            # if 'email' in partner and partner['email']:
            if partner.email:
                # external_user = UserExternal.all_objects.filter(odoo_id=partner["id"]).first()
                odoo_user = self.repo.get_user(partner.id)
                if not odoo_user:
                    email = partner["email"]
                    # exists_by_email = User.all_objects.filter(email=email).first()
                    ordercast_partner = self.ordercast_manager.get_user(email)
                    if ordercast_partner:
                        logger.warning(
                            f"User with email {email} already exists, ignoring."
                        )
                        # existing_external_object = UserExternal.all_objects.filter(user_id=exists_by_email.id).first()
                        existing_odoo_user = self.repo.get_user(ordercast_partner.id)
                        if existing_odoo_user:
                            logger.warning(
                                f"This user already mapped to Odoo id: {existing_odoo_user.odoo_id}, but this user come with id: {partner['id']}."
                            )
                            self.repo.remove_user(existing_odoo_user.odoo_id)
                            # existing_external_object.is_removed = False
                            # existing_external_object.save()
                        else:
                            # UserExternal.all_objects.update_or_create(user_id=exists_by_email.id, odoo_id=partner["id"])
                            self.repo.save_user(
                                OdooUser(
                                    odoo_id=partner["id"],
                                    created_at=datetime.now(timezone.utc),
                                    updated_at=datetime.now(timezone.utc),
                                    sync_date=datetime.now(timezone.utc),
                                    user=ordercast_partner.id,
                                )
                            )
                    else:
                        name = partner["name"]
                        defaults = {
                            "name": name,
                            "erp_id": partner["id"],
                            "is_approved": False,
                            "is_active": True,
                            "is_removed": False,
                            "password": secrets.token_urlsafe(nbytes=64),
                            "status": UserStatus.NEW,
                        }

                        # saved, is_new = User.all_objects.update_or_create(email=email, defaults=defaults)
                        saved = self.ordercast_manager.upsert_user(
                            email=email, defaults=defaults
                        )

                        # UserExternal.all_objects.update_or_create(user_id=saved.id, odoo_id=partner["id"],
                        #                                           defaults={'is_removed': False})
                        self.repo.save_user(
                            OdooUser(
                                odoo_id=partner["id"],
                                created_at=datetime.now(timezone.utc),
                                updated_at=datetime.now(timezone.utc),
                                sync_date=datetime.now(timezone.utc),
                                user=saved.id,
                            )
                        )

                        partner["saved_id"] = saved.id
                        partner["saved"] = saved
                        lang = (
                            partner["language"]
                            if "language" in partner
                            and partner["language"]
                            and len(partner["language"]) == 2
                            else "fr"
                        )
                        defaults = {"language": lang}
                        if not is_empty(partner, "website"):
                            defaults["website"] = partner["website"]
                        if not is_empty(partner, "comment"):
                            defaults["info"] = partner["comment"]
                        # saved_profile, is_new = ProfileSettings.objects.update_or_create(user_id=saved.id,
                        #                                                                  defaults=defaults)
                        user_profile = self.ordercast_manager.create_user_profile(
                            user_id=saved.id, defaults=defaults
                        )
                        partner["profile"] = user_profile
                        self.save_billing_address(
                            partner, saved, self.ordercast_manager
                        )
                        if is_not_empty(partner, "billing_addresses"):
                            for billing_address in partner["billing_addresses"]:
                                self.save_billing_address(
                                    billing_address, saved, self.ordercast_manager
                                )

                        if is_not_empty(partner, "shipping_addresses"):
                            for shipping_address in partner["shipping_addresses"]:
                                name = None
                                if is_not_empty(shipping_address, "name"):
                                    name = shipping_address["name"]
                                address = self.save_address(shipping_address, saved)
                                # shipping, _ = ShippingAddress.objects.update_or_create(name=name, user_id=saved.id,
                                #                                                        address_id=address.id)
                                self.ordercast_manager.create_shipping_address(
                                    user_id=saved.id, name=name, address_id=address.id
                                )
                else:
                    logger.info(
                        f"User with email {partner['email']} already exists with id {odoo_user.user_id}, ignoring."
                    )

    def save_billing_address(
        self, billing_address, saved, ordercast_manager: OrdercastManager
    ):
        if billing_address and saved:
            name = None
            vat = None
            company_name = None
            if is_not_empty(billing_address, "name"):
                name = billing_address["name"]
            if is_not_empty(billing_address, "company_name"):
                company_name = billing_address["company_name"]
            elif name:
                company_name = name
            if is_not_empty(billing_address, "vat"):
                vat = billing_address["vat"]
            address = self.save_address(billing_address, saved)
            # billing_info, _ = BillingInfo.objects.update_or_create(
            #     enterprise_name=company_name, address_id=address.id, vat=vat
            # )
            billing_info = ordercast_manager.create_billing_info(
                enterprise_name=company_name, address_id=address.id, vat=vat
            )
            # billing_ = Billing.objects.update_or_create(
            #     name=name, user_id=saved.id, billing_info_id=billing_info.id
            # )
            return ordercast_manager.create_billing(
                name=name, user_id=saved.id, billing_info_id=billing_info.id
            )

    def save_address(self, address, user):
        if address and user:
            defaults_address = {}
            name = None
            if is_not_empty(address, "company_name"):
                name = address["company_name"]
            elif is_not_empty(address, "name"):
                name = address["name"]
            if is_not_empty(address, "email"):
                defaults_address["email"] = address["email"]
            if is_not_empty(address, "company_name"):
                defaults_address["company_name"] = address["company_name"]
            if is_not_empty(address, "company_name"):
                defaults_address["name"] = address["company_name"]
            if is_not_empty(address, "address_one"):
                defaults_address["address_one"] = address["address_one"]
            if is_not_empty(address, "address_two"):
                defaults_address["address_two"] = address["address_two"]
            if is_not_empty(address, "phone"):
                defaults_address["phone"] = address["phone"]
            if is_not_empty(address, "postal_code"):
                defaults_address["code"] = address["postal_code"]
            if is_not_empty(address, "city"):
                # city = City.objects.filter(name__iexact=address['city']).first()
                city = self.ordercast_manager.get_city(address["city"])
                if city:
                    defaults_address["city"] = city
            if is_not_empty(address, "country_code"):
                # country = Country.objects.filter(code2=address['country_code']).first()
                country = self.ordercast_manager.get_country(
                    code2=address["country_code"]
                )
                if country:
                    defaults_address["country"] = country
            # saved, _ = Address.objects.update_or_create(user_id=user.id, name=name, defaults=defaults_address)
            address = self.ordercast_manager.create_address(
                user_id=user.id, name=name, defaults=defaults_address
            )
            # AddressExternal.objects.update_or_create(address_id=saved.id, odoo_id=address['id'])
            self.repo.save_address(
                OdooAddress(
                    odoo_id=address["id"],
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    sync_date=datetime.now(timezone.utc),
                    address=address.id,
                    original_address_id=address.id,
                )
            )
            return address

    def sync_users_to_odoo(self):
        send_users = True  # todo: extract this to configuration
        if send_users:
            users = self.ordercast_manager.get_users()
            logger.info(f"Loaded users => {len(users)}, started sending them to Odoo.")
            if users:
                self.send_providerab.asd(users)


@lru_cache()
def get_odoo_sync_manager(
    odoo_repo: Annotated[OdooRepo, Depends(get_odoo_repo)],
    odoo_provider: Annotated[OdooManager, Depends(get_odoo_provider)],
    ordercast_manager: Annotated[OrdercastManager, Depends(get_ordercast_manager)],
) -> OdooSyncManager:
    return OdooSyncManager(odoo_repo, odoo_provider, ordercast_manager)
