import sqlalchemy
from sqlalchemy.orm import sessionmaker, declarative_base
# DB: cập nhật nếu dùng PostgreSQL
DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://postgres:minhnguyen1A@localhost:5432/securemail")
# DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///securemail.db")

engine = sqlalchemy.create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()