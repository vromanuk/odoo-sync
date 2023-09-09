from pydantic import BaseModel, PositiveInt


class BulkSignUpByErpIdRequest(BaseModel):
    erp_id: PositiveInt
