from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime

Base = declarative_base()

class LogMetadata(Base):
    __tablename__ = 'log_metadata'
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, nullable=True)  # Not handling sessions in this step
    filename = Column(String, nullable=False)
    upload_time = Column(DateTime, default=datetime.datetime.utcnow)
    log_start_time = Column(DateTime, nullable=True)
    log_end_time = Column(DateTime, nullable=True)
    vehicle_type = Column(String, nullable=True)
    parser_version = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    telemetry = relationship('ParsedTelemetry', back_populates='log', cascade="all, delete-orphan")

class ParsedTelemetry(Base):
    __tablename__ = 'parsed_telemetry'
    id = Column(Integer, primary_key=True, index=True)
    log_id = Column(Integer, ForeignKey('log_metadata.id', ondelete='CASCADE'))
    message_type = Column(String, nullable=False)
    timestamp = Column(Float, nullable=False)
    data = Column(JSON, nullable=False)
    log = relationship('LogMetadata', back_populates='telemetry') 