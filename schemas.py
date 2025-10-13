from pydantic import BaseModel

class URLBase(BaseModel):
    target_url: str

class URLInDB(URLBase):
    is_active: bool
    clicks: int

    class Config:
        # Enabling Object-Relational Mapping
        orm_mode = True

class URLInfo(URLInDB):
    url: str
    admin_url: str