from typing import Union

from .models import (
    OdooProduct,
    OdooCategory,
    OdooProductVariant,
    OdooAttribute,
    OdooOrder,
    OdooUser,
    OdooWarehouse,
    OdooDeliveryOption,
    OdooAddress,
    OdooBasketProduct,
)

OdooEntity = Union[
    OdooProduct
    | OdooCategory
    | OdooProductVariant
    | OdooAttribute
    | OdooOrder
    | OdooUser
    | OdooDeliveryOption
    | OdooWarehouse
    | OdooAddress
    | OdooBasketProduct
]
