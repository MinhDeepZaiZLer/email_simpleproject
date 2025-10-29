from sqlalchemy import text
from backend.database import engine

def migrate():
    """Thêm các cột public_key và private_key_encrypted nếu chưa có"""
    with engine.connect() as conn:
        # Check xem cột đã tồn tại chưa
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='public_key'
        """))
        
        if result.fetchone() is None:
            print("Thêm cột public_key...")
            conn.execute(text("ALTER TABLE users ADD COLUMN public_key TEXT"))
            conn.commit()
        else:
            print("Cột public_key đã tồn tại")
        
        # Check private_key_encrypted
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='private_key_encrypted'
        """))
        
        if result.fetchone() is None:
            print("Thêm cột private_key_encrypted...")
            conn.execute(text("ALTER TABLE users ADD COLUMN private_key_encrypted TEXT"))
            conn.commit()
        else:
            print("Cột private_key_encrypted đã tồn tại")
        
        print("✓ Migration hoàn tất!")

if __name__ == '__main__':
    migrate()