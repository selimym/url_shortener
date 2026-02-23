from pydantic import BaseModel, ConfigDict

class URLBase(BaseModel):
    target_url: str

class URLInDB(URLBase):
    model_config = ConfigDict(from_attributes=True)

    is_active: bool
    clicks: int

class URLInfo(URLInDB):
    url: str
    admin_url: str