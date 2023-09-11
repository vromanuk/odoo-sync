import secrets
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated

import structlog
from fastapi import Depends

from src.data import UserStatus, OdooUser, OdooAddress, OdooProductGroup, OdooProduct
from .helpers import is_empty, is_not_empty, has_objects
from .odoo_manager import OdooManager, get_odoo_provider
from .odoo_repo import OdooRepo, get_odoo_repo, OdooKeys
from .ordercast_manager import OrdercastManager, get_ordercast_manager
from .partner import validate_partners

logger = structlog.getLogger(__name__)


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

        logger.info("Start receiving products from Odoo")
        self.sync_products(full_sync=True)

        logger.info("Start receiving order data from Odoo")
        self.sync_warehouses()

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
        users = self.repo.get_many(key=OdooKeys.USERS)
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
                odoo_user = self.repo.get(key=OdooKeys.USERS, entity_id=partner.id)
                if not odoo_user:
                    email = partner["email"]
                    # exists_by_email = User.all_objects.filter(email=email).first()
                    ordercast_partner = self.ordercast_manager.get_user(email)
                    if ordercast_partner:
                        logger.warning(
                            f"User with email {email} already exists, ignoring."
                        )
                        # existing_external_object = UserExternal.all_objects.filter(user_id=exists_by_email.id).first()
                        existing_odoo_user = self.repo.get(
                            key=OdooKeys.USERS, entity_id=ordercast_partner.id
                        )
                        if existing_odoo_user:
                            logger.warning(
                                f"This user already mapped to Odoo id: {existing_odoo_user.odoo_id}, but this user come with id: {partner['id']}."
                            )
                            self.repo.remove(
                                key=OdooKeys.USERS, entity_id=existing_odoo_user.odoo_id
                            )
                            # existing_external_object.is_removed = False
                            # existing_external_object.save()
                        else:
                            # UserExternal.all_objects.update_or_create(user_id=exists_by_email.id, odoo_id=partner["id"])
                            self.repo.insert(
                                key=OdooKeys.USERS,
                                entity=OdooUser(
                                    odoo_id=partner["id"],
                                    sync_date=datetime.now(timezone.utc),
                                    user=ordercast_partner.id,
                                ),
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
                        self.repo.insert(
                            key=OdooKeys.USERS,
                            entity=OdooUser(
                                odoo_id=partner["id"],
                                sync_date=datetime.now(timezone.utc),
                                user=saved.id,
                            ),
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
            self.repo.insert(
                key=OdooKeys.ADDRESSES,
                entity=OdooAddress(
                    odoo_id=address["id"],
                    sync_date=datetime.now(timezone.utc),
                    address=address.id,
                    original_address_id=address.id,
                ),
            )
            return address

    def sync_users_to_odoo(self):
        send_users = True  # todo: extract this to configuration
        if send_users:
            users = self.ordercast_manager.get_users(odoo_repo=self.repo)
            logger.info(f"Loaded users => {len(users)}, started sending them to Odoo.")
            if users:
                self.odoo_manager.sync_users(users)

    def sync_products(self, full_sync=False):
        # last_sync_date = (
        #     ProductGroupExternal.objects.last_sync_date() if not full_sync else None
        # )
        last_sync_date = (
            None if full_sync else self.repo.get_last_sync_date(OdooProductGroup)
        )
        # groups_dict = self.receive_provider.receive_product_groups(last_sync_date)
        product_groups = self.odoo_manager.get_product_groups(last_sync_date)

        logger.info(f"Connected to Odoo")
        logger.info(
            f"Received {len(product_groups['objects']) if has_objects(product_groups) else 0} groups, start saving them."
        )

        if has_objects(product_groups):
            self.ordercast_manager.save_product_groups(
                product_groups, odoo_repo=self.repo
            )

        # last_sync_date = (
        #     ProductExternal.objects.last_sync_date() if not full_sync else None
        # )
        last_sync_date = (
            None if full_sync else self.repo.get_last_sync_date(OdooProduct)
        )
        products = self.odoo_manager.get_products(last_sync_date)
        has_products = has_objects(products)

        logger.info(
            f"Received {len(products['objects']) if has_products else 0} products."
        )

        if (
            has_products
        ):  # in case when any product is changed sync from begin the categories. bug: when product category changed, but not synced
            category_last_sync_date = None
            logger.info(f"There products are changed, receiving all categories.")
        else:
            # category_last_sync_date = CategoryExternal.objects.last_sync_date()
            category_last_sync_date = self.repo.get_last_sync_date(OdooCategory)

        categories = self.odoo_manager.get_categories(category_last_sync_date)

        logger.info(
            f"Received {len(categories['objects']) if categories['objects'] else 0} categories, start saving them."
        )

        if categories:
            self.ordercast_manager.save_categories(categories)
        if not full_sync:
            last_attribute_name_sync = (
                CategoryExternal.objects.filter(
                    category__category_type=Category.PRODUCT_ATTRIBUTE_TYPE
                )
                .order_by("sync_date")
                .last()
            )
            attribute_category_from_date = None
            if last_attribute_name_sync:
                attribute_category_from_date = last_attribute_name_sync.sync_date

            attributes = self.odoo_manager.get_product_attributes(
                from_date=attribute_category_from_date,
                attribute_from_date=AttributeExternal.objects.last_sync_date(),
            )
        else:
            attributes = self.odoo_manager.get_product_attributes()

        logger.info(
            f"Received {len(attributes['objects']) if attributes['objects'] else 0} attributes with total of {sum([len(a['values']) for a in attributes['objects'] if 'values' in a])} values, start saving them."
        )

        if attributes:
            self.ordercast_manager.save_attributes(attributes, odoo_repo=self.repo)

        if has_products:
            logger.info(
                f"Starting saving products after saving categories and attributes."
            )
            self.ordercast_manager.save_products(
                categories, product_groups, attributes, products, odoo_repo=self.repo
            )

    def sync_warehouses(self):
        delivery_options = self.odoo_manager.receive_delivery_options()
        logger.info(
            f"Received {len(delivery_options['objects']) if delivery_options and 'objects' in delivery_options else 0} delivery options, start saving them."
        )
        if delivery_options:
            self.ordercast_manager.save_delivery_option(
                delivery_options, odoo_repo=self.repo
            )

        warehouses = self.odoo_manager.receive_warehouses()
        logger.info(
            f"Received {len(warehouses['objects']) if warehouses and 'objects' in warehouses else 0} warehouses, start saving them."
        )
        if warehouses:
            self.ordercast_manager.save_warehouse(warehouses, odoo_repo=self.repo)


@lru_cache()
def get_odoo_sync_manager(
    odoo_repo: Annotated[OdooRepo, Depends(get_odoo_repo)],
    odoo_provider: Annotated[OdooManager, Depends(get_odoo_provider)],
    ordercast_manager: Annotated[OrdercastManager, Depends(get_ordercast_manager)],
) -> OdooSyncManager:
    return OdooSyncManager(odoo_repo, odoo_provider, ordercast_manager)
