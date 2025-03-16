from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Float, Text, JSON, func
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True)
    name = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    schedule = Column(String)  # daily, weekly, monthly, immediately
    preferences = relationship("UserPreference", back_populates="user")
    interactions = relationship("UserInteraction", back_populates="user")

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    notification_frequency = Column(String)
    topics = Column(String)
    user = relationship("User", back_populates="preferences")

class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    location_name = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    subject_name = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

class NewsSource(Base):
    __tablename__ = "news_sources"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True)
    name = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True)
    email = Column(String, unique=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    role = Column(String)

class Metrics(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, default=datetime.utcnow)
    total_users = Column(Integer)
    active_users = Column(Integer)
    messages_sent = Column(Integer)
    messages_received = Column(Integer)
    click_through_rate = Column(Float)

class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    content = Column(Text)
    variables = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class ScheduledMessage(Base):
    __tablename__ = "scheduled_messages"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("message_templates.id"))
    scheduled_time = Column(DateTime)
    target_groups = Column(JSON)  # Store target user groups
    personalization_data = Column(JSON)  # Store variables for template
    status = Column(String)  # pending, sent, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    template = relationship("MessageTemplate")

class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    whatsapp_message_id = Column(String(100), nullable=False)
    phone_number = Column(String(20), nullable=False)
    message_type = Column(String(20), nullable=False)  # 'incoming', 'outgoing'
    message_content = Column(Text)
    status = Column(String(20))  # sent, delivered, read, failed
    status_timestamp = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    # If the message failed, store the error details
    error_code = Column(Integer)
    error_title = Column(String(200))
    error_message = Column(Text)

    def __repr__(self):
        return f'<Message {self.whatsapp_message_id}>'

class UserInteraction(Base):
    __tablename__ = "user_interactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    phone_number = Column(String(20), nullable=False)
    category = Column(String(20), nullable=False)  # 'term', 'article', 'news_suggestion'
    query = Column(Text, nullable=False)  # The user's input/question
    response = Column(Text, nullable=False)  # The system's response
    feedback = Column(Boolean, nullable=True)  # User's feedback (True/False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="interactions")

    def __repr__(self):
        return f'<UserInteraction {self.category}:{self.query}>'

class SchedulerRun(Base):
    __tablename__ = "scheduler_runs"

    id = Column(Integer, primary_key=True, index=True)
    task_name = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)  # 'success', 'failed'
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    affected_users = Column(Integer, default=0)  # Number of users affected
    error_message = Column(Text)

    def __repr__(self):
        return f'<SchedulerRun {self.task_name}:{self.status}>'