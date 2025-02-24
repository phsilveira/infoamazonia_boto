from pydantic import BaseModel, EmailStr, HttpUrl
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    phone_number: str

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True

class LocationBase(BaseModel):
    location_name: str
    user_id: Optional[int] = None

class LocationCreate(LocationBase):
    pass

class Location(LocationBase):
    id: int
    latitude: float
    longitude: float
    created_at: datetime

    class Config:
        orm_mode = True

class NewsSourceBase(BaseModel):
    url: HttpUrl
    name: str

class NewsSourceCreate(NewsSourceBase):
    pass

class NewsSource(NewsSourceBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True

class AdminBase(BaseModel):
    username: str
    email: EmailStr

class AdminCreate(AdminBase):
    password: str

class Admin(AdminBase):
    id: int
    is_active: bool
    role: str

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class MetricsBase(BaseModel):
    total_users: int
    active_users: int
    messages_sent: int
    messages_received: int
    click_through_rate: float
    date: datetime

class Metrics(MetricsBase):
    id: int

    class Config:
        orm_mode = True

class UserInteractionBase(BaseModel):
    phone_number: str
    category: str
    query: str
    response: str
    feedback: Optional[bool] = None

class UserInteractionCreate(UserInteractionBase):
    user_id: Optional[int] = None

class UserInteraction(UserInteractionBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True