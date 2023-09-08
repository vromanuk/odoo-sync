from typing import Union

from .models import (
    OdooProductGroup,
    OdooCategory,
    OdooProduct,
    OdooAttribute,
    OdooOrder,
    OdooUser,
    OdooWarehouse,
    OdooDeliveryOption,
    OdooAddress,
    OdooBasketProduct,
)

OdooEntity = Union[
    OdooProductGroup
    | OdooCategory
    | OdooProduct
    | OdooAttribute
    | OdooOrder
    | OdooUser
    | OdooDeliveryOption
    | OdooWarehouse
    | OdooAddress
    | OdooBasketProduct
]
