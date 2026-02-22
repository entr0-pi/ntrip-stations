from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base

class Station(Base):
    __tablename__ = "stations"

    id        = Column(Integer, primary_key=True, index=True)
    mount     = Column(String, nullable=False, index=True)
    city      = Column(String)
    format    = Column(String)
    details   = Column(String)
    network   = Column(String)
    country   = Column(String)
    lat       = Column(Float)
    lon       = Column(Float)
    auth      = Column(String)
    bitrate   = Column(String)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
