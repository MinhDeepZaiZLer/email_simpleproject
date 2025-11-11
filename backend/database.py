from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    email_address = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    public_key = Column(Text, nullable=True)  # THÊM LẠI
    private_key_encrypted = Column(Text, nullable=True)  # THÊM LẠI

class ReceivedEmail(Base):
    __tablename__ = 'received_emails'
    
    id = Column(Integer, primary_key=True)
    recipient_email = Column(String, nullable=False)
    raw_message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
<<<<<<< HEAD
    timestamp = Column(DateTime, default=datetime.utcnow)

# Database connection

DATABASE_URL = "postgresql://postgres:minhnguyen1A@localhost/securemail"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

=======
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    is_spam = Column(Boolean, default=False, nullable=False)
>>>>>>> 0e68846143171547554d34a3e9dbf20e28c7155c
def init_db():
    """Tạo tất cả tables"""
    Base.metadata.create_all(bind=engine)