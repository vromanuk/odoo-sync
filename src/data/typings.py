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
    OdooPriceRate,
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
    | OdooPriceRate
]
