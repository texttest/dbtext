from sqlalchemy import Integer, Column, String, Date, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Wildlife(Base):
    __tablename__ = "wildlife"

    internalId = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100))
    type = Column(String(16))

    observations = relationship("Observation", back_populates="wildlife")


class Observation(Base):
    __tablename__ = "observations"

    internalId = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date)
    wildlifeId = Column(Integer, ForeignKey("wildlife.internalId"))
    wildlife = relationship("Wildlife", back_populates="observations")
