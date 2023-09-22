from typing import Annotated, Any

from fastapi import Depends
from odoo_rpc_client import Client

from src.config import OdooConfig, get_settings, Settings


class OdooClient:
    def __init__(self, config: OdooConfig) -> None:
        self._config = config
        self._client = Client(
            host=self._config.ODOO_HOST,
            dbname=self._config.ODOO_DB,
            user=self._config.ODOO_USER,
            pwd=self._config.ODOO_PASSWORD,
            port=self._config.ODOO_PORT,
            protocol=self._config.ODOO_PROTOCOL,
        )

    def get_objects(
        self, object_name: str, criteria: Any = None, i18n_fields: Any = None
    ) -> Any:
        if criteria is None:
            criteria = []

        remote_results = self._client[object_name].search_read(domain=criteria)
        if i18n_fields:
            self.init_i18n(object_name, remote_results, i18n_fields)
        return remote_results

    def init_i18n(
        self,
        resource: Any,
        list_data: list[dict[str, Any]],
        fields: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        remote_langs = self._client["res.lang"].search_read(domain=[])
        if remote_langs:
            for lang in remote_langs:
                search_fields = ["id"] + fields
                remote_result_list = self._client[resource].search_read(
                    fields=search_fields, domain=[], context={"lang": lang["code"]}
                )
                if remote_result_list:
                    for remote_result in remote_result_list:
                        for data in list_data:
                            if "id" in data and data["id"] == remote_result["id"]:
                                for field in fields:
                                    code = lang["iso_code"]
                                    code = code[0:2] if "_" in code else code
                                    data[field + "_" + code] = remote_result[field]
                                break
        return list_data

    def get_object(self, obj: Any) -> dict[str, Any]:
        if (
            isinstance(obj, list) and len(obj) > 1
        ):  # clear [int, str] mixed lists, leave only fist type
            first_type = None
            remove_item = []
            for item in obj:
                if first_type:
                    if first_type != type(item):
                        remove_item.append(item)
                else:
                    first_type = type(item)
            for remove in remove_item:
                obj.remove(remove)

        return obj

    def get_object_id(self, obj: str) -> Any:
        odoo_object = self.get_object(obj)
        if isinstance(odoo_object, list) and len(odoo_object) > 0:
            return odoo_object[0]
        return odoo_object

    def get_all_object_ids(self, object_name: str, domain: Any = None) -> list[int]:
        if not domain:
            domain = []
        remote_results = self._client[object_name].search_read(
            domain=domain, fields=["id"]
        )

        return [p["id"] for p in remote_results]

    def get_discounts(self) -> str:
        return self._config.ODOO_DISCOUNTS


def get_odoo_client(settings: Annotated[Settings, Depends(get_settings)]) -> OdooClient:
    return OdooClient(settings.ODOO)
