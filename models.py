from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Float, Text, JSON, func
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    schedule = Column(String(20))  # daily, weekly, monthly
    preferences = relationship("UserPreference", back_populates="user", cascade="all, delete-orphan")

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    notification_frequency = Column(String(20))
    topics = Column(String(255))
    user = relationship("User", back_populates="preferences")

class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    location_name = Column(String(100), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    created_at = Column(DateTime, default=datetime.utcnow)

class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    subject_name = Column(String(100), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    created_at = Column(DateTime, default=datetime.utcnow)

class NewsSource(Base):
    __tablename__ = "news_sources"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(255), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String(20), nullable=False)

class Metrics(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, default=datetime.utcnow)
    total_users = Column(Integer, default=0)
    active_users = Column(Integer, default=0)
    messages_sent = Column(Integer, default=0)
    messages_received = Column(Integer, default=0)
    click_through_rate = Column(Float, default=0.0)

class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    variables = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    scheduled_messages = relationship("ScheduledMessage", back_populates="template", cascade="all, delete-orphan")

class ScheduledMessage(Base):
    __tablename__ = "scheduled_messages"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("message_templates.id", ondelete="CASCADE"))
    scheduled_time = Column(DateTime, nullable=False)
    target_groups = Column(JSON)
    personalization_data = Column(JSON)
    status = Column(String(20), nullable=False)  # pending, sent, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    template = relationship("MessageTemplate", back_populates="scheduled_messages")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_message_id = Column(String(100), unique=True, nullable=False)
    phone_number = Column(String(20), nullable=False)
    message_type = Column(String(20), nullable=False)  # incoming, outgoing
    message_content = Column(Text)
    status = Column(String(20))  # sent, delivered, read, failed
    status_timestamp = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    error_code = Column(Integer)
    error_title = Column(String(200))
    error_message = Column(Text)

    def __repr__(self):
        return f"<Message {self.whatsapp_message_id}>"