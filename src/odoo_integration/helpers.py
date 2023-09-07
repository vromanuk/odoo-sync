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
