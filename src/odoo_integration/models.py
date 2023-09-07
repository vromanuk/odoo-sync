from datetime import datetime

from pydantic import BaseModel, PositiveInt

from .enums import CategoryType, OrderStatus, InvoiceStatus
from .helpers import is_not_empty


class OdooProductGroup(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    product_group: PositiveInt


class OdooCategory(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    category: PositiveInt
    category_type: CategoryType


class OdooProduct(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    product: PositiveInt


class OdooAttribute(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    attribute: PositiveInt


class OdooOrder(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    order: PositiveInt
    odoo_order_status: OrderStatus
    odoo_invoice_status: InvoiceStatus


class OdooUser(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    user: PositiveInt


class OdooDeliveryOption(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    delivery_option: PositiveInt


class OdooWarehouse(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    warehouse: PositiveInt


class OdooAddress(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    address: PositiveInt
    original_address_id: PositiveInt


class OdooBasketProduct(BaseModel):
    odoo_id: PositiveInt
    created_at: datetime
    updated_at: datetime
    sync_date: datetime
    basket_product: PositiveInt


class Partner:
    @classmethod
    def build_from(cls, odoo_client, partner, remote_supported_langs=None):
        partner_dto = {"id": partner["id"], "_remote_id": partner["id"]}
        if is_not_empty(partner, "street"):
            partner_dto["address_one"] = partner["street"]
        if is_not_empty(partner, "zip"):
            partner_dto["postal_code"] = partner["zip"]
        if is_not_empty(partner, "street2"):
            partner_dto["address_two"] = partner["street2"]
        if is_not_empty(partner, "name"):
            partner_dto["name"] = partner["name"]
        if is_not_empty(partner, "email"):
            partner_dto["email"] = partner["email"]
        if is_not_empty(partner, "website"):
            partner_dto["website"] = partner["website"]
        if is_not_empty(partner, "comment"):
            partner_dto["comment"] = partner["comment"]
        if is_not_empty(partner, "phone"):
            partner_dto["phone"] = partner["phone"]
        if is_not_empty(partner, "city"):
            partner_dto["city"] = partner["city"]
        if is_not_empty(partner, "lang") and remote_supported_langs:
            language_iso = partner["lang"]
            for lang in remote_supported_langs:
                if lang["code"] == language_iso:
                    partner_dto["language"] = lang["iso_code"]
                    break
        if is_not_empty(partner, "type"):
            partner_dto["type"] = partner["type"]
        if is_not_empty(partner, "parent_id"):
            partner_dto["parent_id"] = odoo_client.get_object_id(partner["parent_id"])
        # if partner['country_id']:
        #     remote_country = remote_country_obj.search_read([('id', '=', partner['country_id'])])
        #     if remote_country:
        #         partner_dto["country_name"] = remote_country['name']
        if is_not_empty(partner, "country_code"):
            partner_dto["country_code"] = partner["country_code"]
        if is_not_empty(partner, "state_id"):
            if type(partner["state_id"]) == list and len(partner["state_id"]) == 2:
                partner_dto["state_name"] = partner["state_id"][1]
        if is_not_empty(partner, "vat"):
            partner_dto["vat"] = partner["vat"]
        if is_not_empty(partner, "commercial_company_name"):
            partner_dto["company_name"] = partner["commercial_company_name"]
        return partner_dto
