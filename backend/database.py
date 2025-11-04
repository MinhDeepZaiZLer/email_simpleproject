# Trong backend/database.py hoặc backend/models.py
import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
import datetime

# --- Phần kết nối PostgreSQL ---
DATABASE_URL = "postgresql://postgres:minhnguyen1A@localhost/securemail"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Định nghĩa Models ---

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    email_address = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    public_key = Column(Text, nullable=True)  # Thêm lại
    private_key_encrypted = Column(Text, nullable=True)  # Thêm lại

class ReceivedEmail(Base):
    """Bảng lưu trữ mail thô mà SMTP server nhận được"""
    __tablename__ = "received_emails"
    id = Column(Integer, primary_key=True, index=True)
    
    # Mail này dành cho ai
    recipient_email = Column(String, index=True, nullable=False)
    
    # Nội dung mail thô (bao gồm headers, body đã mã hoá, chữ ký)
    raw_message = Column(Text, nullable=False) 
    
    is_read = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    is_spam = Column(Boolean, default=False, nullable=False)
def init_db():
    """Hàm tạo bảng (chạy một lần khi setup)"""
    Base.metadata.create_all(bind=engine)

# Nếu bạn chạy file này trực tiếp, nó sẽ tạo bảng
if __name__ == "__main__":
    print("Khởi tạo cơ sở dữ liệu...")
    init_db()
    print("Hoàn tất.")