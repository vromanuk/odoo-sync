from typing import Optional

from pydantic import BaseModel, PositiveInt


class OrdercastCommon(BaseModel):
    id: PositiveInt
    name: str


class OrdercastMerchant(OrdercastCommon):
    erp_id: Optional[str]


class OrdercastProduct(OrdercastCommon):
    sku: str


class OrdercastAttribute(OrdercastCommon):
    pass


class OrdercastCategory(OrdercastCommon):
    code: str
