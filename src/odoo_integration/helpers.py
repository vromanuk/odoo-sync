import re
from typing import Any

import regex as regexp

from .constants import SUPPORTED_LANGUAGES


def is_not_empty(values_dict, key):
    return not is_empty(values_dict, key)


def is_empty(values_dict, key):
    return (
        key not in values_dict
        or not values_dict[key]
        or str(values_dict[key]).strip() == ""
    )


def is_unique_by(unique_values, dict_object, key):
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


def get_i18n_field_as_dict(data: dict, field, rename_field=None, reg_exp=None):
    if data and field:
        result = dict()
        field_name = rename_field if rename_field else field
        for lang_code, lang_val in SUPPORTED_LANGUAGES.items():
            i18n_field = field + "_" + lang_code
            rename_i18n_field = field_name + "_" + lang_code
            default_value = data[field] if field in data else None
            if i18n_field in data:
                final_value = data[i18n_field]
            else:
                final_value = default_value
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
