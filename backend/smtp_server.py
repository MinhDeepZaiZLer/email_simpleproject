import asyncio
from aiosmtpd.controller import Controller
from backend.database import SessionLocal
from backend.database import ReceivedEmail # Sửa import nếu cần
import email # Dùng để parse mail
from email.header import decode_header # Thêm import này
import joblib # Dùng để load mô hình
import re # Thêm import này

# --- Load mô hình spam filter ---
try:
    SPAM_MODEL = joblib.load('spam_model.pkl')
    print("Đã load thành công mô hình Spam Filter.")
except FileNotFoundError:
    print("LỖI: Không tìm thấy file 'spam_model.pkl'. Hãy chạy 'train_spam_model.py' trước.")
    SPAM_MODEL = None

# --- [MỚI] Hàm dọn dẹp (PHẢI GIỐNG HỆT file train) ---
def clean_text(text):
    """Hàm dọn dẹp văn bản thô"""
    text = str(text).lower() # Chuyển sang chữ thường
    # text = re.sub(r'subject:', '', text, flags=re.IGNORECASE) # <-- XÓA DÒNG NÀY
    text = re.sub(r'http\S+|www\S+', ' ', text) # Xóa URLs
    text = re.sub(r'\S+@\S+', ' ', text) # Xóa email
    text = re.sub(r'[\d\W_]+', ' ', text) # Xóa số, ký tự đặc biệt, dấu '_'
    text = re.sub(r'\s+', ' ', text).strip() # Xóa khoảng trắng thừa
    return text

def decode_mime_str(s):
    """Decode MIME encoded string (như là Subject)"""
    if s is None:
        return ""
    decoded_parts = decode_header(s)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return ''.join(result)

def get_email_body(msg: email.message.Message) -> str:
    """Helper: Lấy nội dung text từ email (kể cả multipart)"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))

            if ctype == 'text/plain' and 'attachment' not in cdispo:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='replace')
                    break 
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='replace')
    
    # Dọn dẹp các dấu ngắt dòng mềm (=) của Quoted-Printable
    body = re.sub(r'=\s*(\r\n|\r|\n)', '', body).strip()
    
    return body

class CustomSMTPHandler:
    """Xử lý mail nhận được: Lưu vào CSDL VÀ KIỂM TRA SPAM"""
    
    async def handle_DATA(self, server, session, envelope):
        print(f'Nhận mail từ: {envelope.mail_from}')
        print(f'Gửi tới: {envelope.rcpt_tos}')
        
        raw_data_bytes = envelope.content
        
        # --- Phân tích và dự đoán Spam (Subject + Body) ---
        is_spam_result = False
        full_text_content = ""
        try:
            # 1. Parse email
            msg = email.message_from_bytes(raw_data_bytes)
            
            # 2. Lấy Subject VÀ Body
            subject_text = decode_mime_str(msg['Subject'])
            email_body_text = get_email_body(msg)
            
            # 3. [SỬA LỖI] Gộp và DỌN DẸP SẠCH
            full_text_to_clean = f"{subject_text} {email_body_text}"
            full_text_content = clean_text(full_text_to_clean) # <-- ÁP DỤNG HÀM CLEAN
            
            # 4. Dự đoán trên nội dung SẠCH
            if SPAM_MODEL and full_text_content.strip():
                prediction = SPAM_MODEL.predict([full_text_content])
                if prediction[0] == 'spam':
                    is_spam_result = True
            
            print(f"Phân loại Spam: {is_spam_result} (Nội dung SẠCH: '{full_text_content[:70]}...')")

        except Exception as e:
            print(f"Lỗi khi phân tích spam: {e}")

        # --- Lưu vào CSDL ---
        recipients = envelope.rcpt_tos
        if not recipients:
            return '550 No recipients specified'
            
        db = SessionLocal()
        try:
            for email_addr in recipients:
                new_mail = ReceivedEmail(
                    recipient_email=email_addr,
                    raw_message=raw_data_bytes.decode('utf-8', errors='replace'),
                    is_spam=is_spam_result # <-- Lưu kết quả
                )
                db.add(new_mail)
            db.commit()
            
            print(f'Đã lưu mail cho {recipients} (Spam={is_spam_result}).')
            
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
    
    controller.start()
    
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