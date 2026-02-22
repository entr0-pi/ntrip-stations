from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Country(Base):
    __tablename__ = "countries"

    code = Column(String(2), primary_key=True)
    name = Column(String, nullable=False)


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
