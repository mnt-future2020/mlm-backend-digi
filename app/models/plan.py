"""Plan models"""
from pydantic import BaseModel, Field
from typing import Optional

class PlanCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    amount: float = Field(..., gt=0)
    pv: int = Field(..., gt=0)
    referralIncome: float = Field(default=0)
    matchingIncome: float = Field(default=0)
    dailyCapping: float = Field(default=500)
    description: Optional[str] = None
    isActive: bool = Field(default=True)

class PlanUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    pv: Optional[int] = None
    referralIncome: Optional[float] = None
    matchingIncome: Optional[float] = None
    dailyCapping: Optional[float] = None
    description: Optional[str] = None
    isActive: Optional[bool] = None
