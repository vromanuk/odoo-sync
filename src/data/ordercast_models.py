from datetime import datetime
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


class OrdercastOrder(OrdercastCommon):
    id: PositiveInt
    created_at: datetime
    updated_at: datetime


class OrdercastOrderStatus(OrdercastCommon):
    id: PositiveInt
    name: str
    enum: int
