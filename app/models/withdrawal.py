"""Withdrawal models"""
from pydantic import BaseModel, Field
from typing import Optional

class WithdrawalRequest(BaseModel):
    amount: float = Field(..., gt=0)
    paymentMethod: Optional[str] = Field(default="Bank Transfer")
    remarks: Optional[str] = None
