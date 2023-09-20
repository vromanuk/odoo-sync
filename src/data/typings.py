from typing import Union

from .models import (
    OdooProduct,
    OdooCategory,
    OdooProductVariant,
    OdooAttribute,
    OdooOrder,
    OdooUser,
    OdooPickupLocation,
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
    | OdooPickupLocation
    | OdooAddress
    | OdooBasketProduct
    | OdooPriceRate
]
