"""User models"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
import re

class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    mobile: str = Field(..., pattern=r'^[0-9]{10}$')
    referralId: str = Field(..., description="Sponsor's referral ID")
    placement: str = Field(..., pattern=r'^(LEFT|RIGHT)$')
    planId: Optional[str] = None

    @field_validator('username')
    def username_alphanumeric(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username must be alphanumeric')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    mobile: Optional[str] = None
    isActive: Optional[bool] = None
