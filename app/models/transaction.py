"""Transaction models"""
from pydantic import BaseModel, Field
from typing import Optional

class TransactionCreate(BaseModel):
    userId: str
    type: str
    amount: float = Field(..., gt=0)
    description: Optional[str] = None
    pv: Optional[int] = None
    status: str = Field(default="COMPLETED")
