from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import Session
import smtplib
import poplib
import email
from email.message import EmailMessage
from email.header import decode_header
import os
import traceback # Thêm import này

from backend.database import get_db, SessionLocal
from backend.database import User, ReceivedEmail # Đảm bảo import User, ReceivedEmail từ database.py
from backend import crypto_utils

app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/static')
app.config['SECRET_KEY'] = os.urandom(24)

# --- Cổng máy chủ ---
SMTP_SERVER_HOST = 'localhost'
SMTP_SERVER_PORT = 8025
POP3_SERVER_HOST = 'localhost'
POP3_SERVER_PORT = 110

@app.before_request
def load_user():
    """Load user vào 'g' nếu đã login"""
    if 'user_id' in session:
        db = SessionLocal()
        g.user = db.query(User).filter(User.id == session['user_id']).first()
        db.close()
    else:
        g.user = None

def get_current_user():
    """Helper để lấy user"""
    if 'user' in g:
        return g.user
    return None

def decode_mime_str(s):
    """Decode MIME encoded string"""
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

@app.route('/')
def index():
    if g.user:
        return redirect(url_for('inbox'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db: Session = next(get_db())
        username = request.form['username']
        email_addr = request.form['email']
        password = request.form['password']
        
        if db.query(User).filter(User.email_address == email_addr).first():
            flash('Email đã tồn tại.', 'error')
            db.close()
            return redirect(url_for('register'))
        
        # --- THÊM MỚI LOGIC MÃ HOÁ ---
        # 1. Tạo cặp key mới cho user
        try:
            public_key_pem, private_key_pem = crypto_utils.generate_rsa_keys()
            
            # (Bạn có thể thêm bước mã hoá private_key_pem bằng password ở đây)
            
            new_user = User(
                username=username,
                email_address=email_addr,
                password_hash=generate_password_hash(password),
                public_key=public_key_pem,
                private_key_encrypted=private_key_pem # Lưu key vào CSDL
            )
            db.add(new_user)
            db.commit()
            flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
        
        except Exception as e:
            db.rollback()
            flash(f'Lỗi khi tạo key: {e}', 'error')
        finally:
            db.close()
            
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db: Session = next(get_db())
        email_addr = request.form['email']
        password = request.form['password']
        
        user = db.query(User).filter(User.email_address == email_addr).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['password'] = password  # Lưu pass cho POP3
            db.close()
            return redirect(url_for('inbox'))
        else:
            flash('Email hoặc mật khẩu không đúng.', 'error')
            db.close()
            return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/inbox')
def inbox():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    display_emails = []
    db: Session = next(get_db()) # Cần CSDL để lấy key của người gửi
    
    try:
        # Kết nối POP3
        pop_conn = poplib.POP3(POP3_SERVER_HOST, POP3_SERVER_PORT)
        pop_conn.user(user.email_address)
        pop_conn.pass_(session['password'])
        
        num_messages = len(pop_conn.list()[1])
        
        for i in range(num_messages):
            try:
                # Lấy email
                raw_email_lines = pop_conn.retr(i + 1)[1]
                raw_email_data = b'\r\n'.join(raw_email_lines)
                
                # Parse email
                msg = email.message_from_bytes(raw_email_data)
                
                # Decode headers
                from_addr = decode_mime_str(msg['From'])
                subject = decode_mime_str(msg['Subject'])
                
                # --- THAY ĐỔI LOGIC LẤY BODY VÀ GIẢI MÃ ---
                
                # Lấy body (là JSON string hoặc plain text)
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == 'text/plain':
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

                # Kiểm tra xem đây có phải email mã hoá của chúng ta không
                if msg['X-CryptoMail-Version'] == '1.0':
                    # Đây là mail mã hoá
                    sender = db.query(User).filter(User.email_address == from_addr).first()
                    
                    if not sender or not sender.public_key:
                        raise Exception("Không tìm thấy public key của người gửi.")
                    if not user.private_key_encrypted:
                        raise Exception("Bạn không có private key để giải mã.")

                    # Gọi hàm giải mã
                    decrypted_body, is_verified = crypto_utils.unpackage_encrypted_email(
                        body, # body bây giờ là JSON
                        user.private_key_encrypted,
                        sender.public_key
                    )
                    
                    display_emails.append({
                        'subject': subject or '(Không có tiêu đề)',
                        'from': from_addr or '(Không rõ)',
                        'body': decrypted_body, # Hiển thị body đã giải mã
                        'verified': is_verified # True hoặc False
                    })
                
                else:
                    # Đây là mail thường (không mã hoá, vd: từ hệ thống khác)
                    display_emails.append({
                        'subject': subject or '(Không có tiêu đề)',
                        'from': from_addr or '(Không rõ)',
                        'body': body or '(Email trống)',
                        'verified': 'N/A' # Không áp dụng
                    })
                
                # pop_conn.dele(i + 1) # Vô hiệu hoá để không xoá mail
                
            except Exception as e:
                print(f"Lỗi khi xử lý email {i+1}: {e}")
                traceback.print_exc() # In chi tiết lỗi
                display_emails.append({
                    'subject': decode_mime_str(msg.get('Subject', '(Lỗi)')) if 'msg' in locals() else '(Lỗi)',
                    'from': decode_mime_str(msg.get('From', '(Lỗi)')) if 'msg' in locals() else '(Lỗi)',
                    'body': f'[Không thể đọc email: {str(e)}]',
                    'verified': False
                })

        pop_conn.quit()
        
    except Exception as e:
        flash(f'Lỗi khi kết nối POP3: {e}', 'error')
        traceback.print_exc()
    finally:
        db.close() # Luôn đóng CSDL
    
    return render_template('inbox.html', emails=display_emails)

@app.route('/compose', methods=['GET', 'POST'])
def compose():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        db: Session = next(get_db())
        
        recipient_email = request.form['to']
        subject = request.form['subject']
        body = request.form['body']
        
        # --- THAY ĐỔI LỚN BẮT ĐẦU TỪ ĐÂY ---
        
        # 1. Kiểm tra xem người dùng có muốn mã hóa không
        should_encrypt = 'encrypt' in request.form
        
        # 2. Lấy thông tin người nhận
        recipient = db.query(User).filter(User.email_address == recipient_email).first()
        
        if not recipient:
            flash('Không tìm thấy người nhận trong hệ thống.', 'error')
            db.close()
            return render_template('compose.html')
            
        try:
            # 3. Tạo đối tượng EmailMessage
            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = user.email_address
            msg['To'] = recipient_email
            
            flash_message = "" # Chuẩn bị thông báo

            if should_encrypt:
                # --- LOGIC MÃ HOÁ (NẾU CHECKBOX ĐƯỢC CHỌN) ---
                
                # Kiểm tra key
                if not recipient.public_key:
                    flash(f'Người nhận {recipient_email} không có public key, không thể mã hoá.', 'error')
                    db.close()
                    return render_template('compose.html')
                if not user.private_key_encrypted:
                    flash(f'Bạn không có private key, không thể ký email.', 'error')
                    db.close()
                    return render_template('compose.html')

                # Gọi hàm đóng gói (mã hoá + ký)
                json_package = crypto_utils.package_encrypted_email(
                    body,
                    user.private_key_encrypted,
                    recipient.public_key
                )
                
                msg['X-CryptoMail-Version'] = '1.0' # Header tuỳ chỉnh
                msg.set_content(json_package, charset='utf-8') # Body là JSON
                flash_message = 'Email đã được gửi (Đã mã hoá & ký)!'

            else:
                # --- LOGIC GỬI MAIL THƯỜNG (NẾU KHÔNG CHỌN) ---
                msg.set_content(body, charset='utf-8') # Body là plain text
                flash_message = 'Email đã được gửi (Không mã hoá).'

            # 4. Gửi qua SMTP (gửi cả 2 trường hợp)
            with smtplib.SMTP(SMTP_SERVER_HOST, SMTP_SERVER_PORT) as server:
                server.send_message(msg)
                
            flash(flash_message, 'success')
            db.close()
            return redirect(url_for('inbox'))
            
        except Exception as e:
            flash(f'Lỗi khi gửi mail: {e}', 'error')
            traceback.print_exc()
            db.close()
        
    return render_template('compose.html')
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        db: Session = next(get_db())
        
        recipient_email = request.form['to']
        subject = request.form['subject']
        body = request.form['body']
        
        # Kiểm tra người nhận
        recipient = db.query(User).filter(User.email_address == recipient_email).first()
        
        if not recipient:
            flash('Không tìm thấy người nhận trong hệ thống.', 'error')
            db.close()
            return render_template('compose.html')
            
        # --- THÊM MỚI: KIỂM TRA KEY ---
        if not recipient.public_key:
            flash(f'Người nhận {recipient_email} không có public key, không thể mã hoá.', 'error')
            db.close()
            return render_template('compose.html')
        
        if not user.private_key_encrypted:
            flash(f'Bạn không có private key, không thể ký email.', 'error')
            db.close()
            return render_template('compose.html')
            
        try:
            # --- THAY ĐỔI LOGIC: MÃ HOÁ VÀ KÝ ---
            
            # 1. Gọi hàm đóng gói (mã hoá + ký)
            json_package = crypto_utils.package_encrypted_email(
                body,
                user.private_key_encrypted,
                recipient.public_key
            )

            # 2. Tạo email
            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = user.email_address
            msg['To'] = recipient_email
            msg['X-CryptoMail-Version'] = '1.0' # Header tuỳ chỉnh
            msg.set_content(json_package, charset='utf-8') # Body bây giờ là JSON
            
            # 3. Gửi qua SMTP
            with smtplib.SMTP(SMTP_SERVER_HOST, SMTP_SERVER_PORT) as server:
                server.send_message(msg)
                
            flash('Email đã được gửi (Đã mã hoá & ký)!', 'success')
            db.close()
            return redirect(url_for('inbox'))
            
        except Exception as e:
            flash(f'Lỗi khi gửi mail: {e}', 'error')
            traceback.print_exc()
            db.close()
        
    return render_template('compose.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)