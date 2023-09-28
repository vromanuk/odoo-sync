import re
from collections import defaultdict
from typing import Any, Optional, Callable, Iterable

import regex as regexp
import unicodedata

from ..constants import SUPPORTED_LANGUAGES


def is_not_empty(values_dict: dict[str, Any], key: str) -> bool:
    return not is_empty(values_dict, key)


def is_empty(values_dict: dict[str, Any], key: str) -> bool:
    return (
        key not in values_dict
        or not values_dict[key]
        or str(values_dict[key]).strip() == ""
    )


def is_unique_by(
    unique_values: set[Any], dict_object: dict[str, Any], key: str
) -> bool:
    if key in dict_object and dict_object[key]:
        key_value = dict_object[key]
        if key_value in unique_values:
            return False
        else:
            unique_values.add(key_value)
    return True


def is_length_not_in_range(value, min_length, max_length):
    res = is_length_in_range(value, min_length, max_length)
    return res is not None and not res


def is_length_in_range(value, min_length, max_length):
    if value and min_length and max_length:
        local_val = str(value).strip()
        return min_length <= len(local_val) <= max_length


def get_i18n_field_as_dict(
    data: dict,
    field: str,
    rename_field: Optional[str] = None,
    reg_exp: Optional[str] = None,
) -> dict[str, Any]:
    result = {}
    field_name = rename_field or field
    default_value = data.get(field)

    for lang_code, lang_val in SUPPORTED_LANGUAGES.items():
        i18n_field = f"{field}_{lang_code}"
        rename_i18n_field = f"{field_name}_{lang_code}"
        final_value = data.get(i18n_field, default_value)

        if reg_exp:
            result[rename_i18n_field] = re.sub(reg_exp, "", final_value)
        else:
            result[rename_i18n_field] = final_value

    return result


def get_field_with_i18n_fields(data: dict, field, rename_field=None, reg_exp=None):
    i18n_fields_dict = get_i18n_field_as_dict(data, field, rename_field, reg_exp)
    if i18n_fields_dict:
        result = [field]
        for key in i18n_fields_dict:
            result.append(key)

        return result


def is_format(value, fmt):
    if value and fmt:
        return regexp.match(fmt, value, regexp.IGNORECASE)


def is_not_ref(value):
    res = is_ref(value)
    return res is not None and not res


def is_ref(value):
    ref_regexp = r"^[\w\-\.]*$"
    return is_format(value, ref_regexp)


def has_objects(entities: dict[str, Any]) -> bool:
    return entities and "objects" in entities and len(entities["objects"]) > 0


def exists_in_all_ids(entity_id: int, entity: dict[str, Any]) -> bool:
    if entity and "all_ids" in entity:
        return entity_id in entity["all_ids"]


def str_to_float(data, default=None):
    if not data:
        return default
    try:
        if "," in data:
            if "." in data:
                data = data.replace(",", "")
            else:
                data = data.replace(",", ".")
        return float(data.strip()) if data else default
    except ValueError:
        return default


def str_to_int(data, default=None):
    num = str_to_float(data, default)
    return int(num) if num is not None else default


def check_remote_id(dto):
    if "_remote_id" not in dto:
        msg = f"Not remote id found for {dto['id']}. Please check it."
        raise SyntaxError(msg)


def get_entity_name_as_i18n(
    entities: list[dict[str, Any]], prefix: str = "name_"
) -> dict[int, Any]:
    """
    Transforms entities with translated names into a dictionary mapping entity IDs
    to language-specific names.

    :param prefix: The prefix used in the entity keys to identify language-specific names.
                   Default is "name_".
    :param entities: List of dictionaries with keys like "name_language" (e.g., "name_de" for German).
                     Values are the translated names in respective languages.
                     Example: {"name_de": "German Name", "name_fr": "French Name"}

    :return: Dictionary where each entity ID maps to language-to-name mappings.
             Example: {1: {"de": "German Name", "fr": "French Name"},
                       2: {"de": "German Name 2", "fr": "French Name 2"}, ...}
    """
    entities_names = defaultdict(dict)
    for entity in entities:
        for k, v in entity.items():
            if k.startswith(prefix):
                locale = k[len(prefix) :]
                entities_names[entity["id"]][locale] = v

    return entities_names


def slugify(value: str) -> str:
    """
    Converts a string to a URL slug.

    >>> slugify(" Joel is a slug ")
    "joel-is-a-slug"
    """
    if not value:
        return value

    # Unicode isn't allowed
    value = (
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


def set_user_ordercast_id(
    users_to_sync: list[dict[str, Any]], source: Callable[..., Iterable]
) -> list[dict[str, Any]]:
    result = []

    user_mapper = {u["erp_id"]: u for u in users_to_sync}
    synced_users = source()

    for synced_user in synced_users:
        if synced_user.erp_id and (user := user_mapper.get(int(synced_user.erp_id))):
            user["ordercast_id"] = synced_user.id
            result.append(user)

    return result


def set_ordercast_id(
    items: list[dict[str, Any]], source: Callable[..., Iterable], key: str = "code"
) -> list[dict[str, Any]]:
    result = []

    mapper = {slugify(i["name"]): i for i in items}
    synced = source()

    for item in synced:
        if mapped_item := mapper.get(getattr(item, key, None)):
            mapped_item["ordercast_id"] = item.id
            result.append(mapped_item)

    return result
