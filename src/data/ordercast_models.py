from typing import Optional

from pydantic import BaseModel, PositiveInt


class OrdercastMerchant(BaseModel):
    id: PositiveInt
    name: str
    erp_id: Optional[str]
