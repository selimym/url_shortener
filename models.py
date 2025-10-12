from sqlalchemy import Boolean, Column, Integer, String

from database import Base

class URL(Base):
    __tablename__ = "urls"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)
    secret_key = Column(String, unique=True, index=True) #For user to manage url
    target_url = Column(String, index=True)
    is_active = Column(Boolean, default=True) #Failsafe to allow user to cancel delete
    clicks = Column(Integer, default=0)