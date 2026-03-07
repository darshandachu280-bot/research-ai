from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

SQLALCHEMY_DATABASE_URL = "sqlite:///./research_assistant.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String); email = Column(String, unique=True, index=True); hashed_password = Column(String)
    profile_pic = Column(String, default=None)
    role = Column(String, default="Researcher")
    ai_personality = Column(String, default="Professional Researcher")
    project_status = Column(String, default="In Progress")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String); user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="processing"); uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    question = Column(Text); answer = Column(Text); sources = Column(Text) 
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()