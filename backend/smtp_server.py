import asyncio
from aiosmtpd.controller import Controller
from backend.database import SessionLocal
from backend.database import ReceivedEmail
import email

class CustomSMTPHandler:
    """Xử lý mail nhận được: Lưu vào CSDL"""
    
    async def handle_DATA(self, server, session, envelope):
        print(f'Nhận mail từ: {envelope.mail_from}')
        print(f'Gửi tới: {envelope.rcpt_tos}')
        
        # 'data' là nội dung mail thô (bytes)
        raw_data = envelope.content.decode('utf-8', errors='replace')
        
        # Parse người nhận
        recipients = envelope.rcpt_tos
        if not recipients:
            return '550 No recipients specified'
            
        db = SessionLocal()
        try:
            # Lưu mail này cho TẤT CẢ người nhận
            for email_addr in recipients:
                new_mail = ReceivedEmail(
                    recipient_email=email_addr,
                    raw_message=raw_data
                )
                db.add(new_mail)
            
            db.commit()
            print(f'Đã lưu mail cho {recipients} vào CSDL.')
        except Exception as e:
            print(f'Lỗi CSDL: {e}')
            db.rollback()
            return '550 Internal server error'
        finally:
            db.close()
            
        return '250 OK'
async def run_smtp_server():
    handler = CustomSMTPHandler()
    controller = Controller(handler, hostname='localhost', port=8025)
    print("SMTP Server đang chạy ở localhost:8025...")
    
    # Bắt đầu controller (nó chạy trong nền)
    controller.start()
    
    # Dòng này tạo một Event và 'await' nó mãi mãi.
    # Nó giữ cho coroutine này (và event loop) chạy
    # cho đến khi bạn nhấn Ctrl+C.
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        print("\nEvent loop đã bị hủy.")
    finally:
        controller.stop()
        print("Đã dừng SMTP server.")


if __name__ == '__main__':
    try:
        asyncio.run(run_smtp_server())
    except KeyboardInterrupt:
        print("\nĐã nhận tín hiệu (Ctrl+C), đang tắt server...")