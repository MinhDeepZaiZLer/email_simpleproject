import socketserver
import traceback
from email import policy
from email.parser import Parser
from email.header import decode_header
from backend.database import SessionLocal
from backend.database import User, ReceivedEmail
from werkzeug.security import check_password_hash

# --- Trạng thái của POP3 session ---
STATE_AUTH_USER = 1
STATE_AUTH_PASS = 2
STATE_TRANSACTION = 3

class POP3Handler(socketserver.BaseRequestHandler):
    """Xử lý kết nối POP3"""
    
    def setup(self):
        print(f"Kết nối mới từ: {self.client_address}")
        self.state = STATE_AUTH_USER
        self.user = None
        self.user_db = None
        self.user_email = None
        self.mailbox = []
        self.marked_for_deletion = set()
        self.send_response("+OK POP3 server sẵn sàng")

    def send_response(self, msg):
        """Gửi response an toàn với error handling"""
        try:
            self.request.sendall(f"{msg}\r\n".encode('utf-8'))
        except Exception as e:
            print(f"Lỗi khi gửi response: {e}")

    def handle(self):
        while True:
            try:
                raw_data = self.request.recv(1024)
                if not raw_data:
                    break
                
                data = raw_data.decode('utf-8').strip()
                if not data:
                    continue
                
                print(f"[{self.client_address}] RECV: {data}")
                
                parts = data.split()
                command = parts[0].upper()
                
                if command == 'QUIT':
                    self.handle_quit()
                    break
                
                if self.state == STATE_AUTH_USER:
                    if command == 'USER':
                        self.handle_user(parts[1] if len(parts) > 1 else "")
                    else:
                        self.send_response("-ERR Lệnh không hợp lệ")
                
                elif self.state == STATE_AUTH_PASS:
                    if command == 'PASS':
                        self.handle_pass(parts[1] if len(parts) > 1 else "")
                    else:
                        self.send_response("-ERR Cần lệnh PASS")
                
                elif self.state == STATE_TRANSACTION:
                    if command == 'STAT':
                        self.handle_stat()
                    elif command == 'LIST':
                        self.handle_list()
                    elif command == 'RETR':
                        self.handle_retr(parts[1] if len(parts) > 1 else "")
                    elif command == 'DELE':
                        self.handle_dele(parts[1] if len(parts) > 1 else "")
                    elif command == 'NOOP':
                        self.send_response("+OK")
                    elif command == 'RSET':
                        self.handle_rset()
                    else:
                        self.send_response("-ERR Lệnh không hợp lệ")
                        
            except Exception as e:
                print(f"Lỗi trong handle: {e}")
                traceback.print_exc()
                try:
                    self.send_response("-ERR Lỗi server")
                except:
                    pass
                break
        print(f"Đóng kết nối từ: {self.client_address}")

    def handle_user(self, email):
        try:
            db = SessionLocal()
            self.user_db = db.query(User).filter(User.email_address == email).first()
            db.close()
            
            if self.user_db:
                self.user_email = email
                self.state = STATE_AUTH_PASS
                self.send_response(f"+OK User {email} được chấp nhận, chờ password")
            else:
                self.send_response("-ERR Không tìm thấy user")
        except Exception as e:
            print(f"Lỗi handle_user: {e}")
            traceback.print_exc()
            self.send_response("-ERR Lỗi server")

    def handle_pass(self, password):
        try:
            if self.user_db and check_password_hash(self.user_db.password_hash, password):
                self.state = STATE_TRANSACTION
                self.load_mailbox()
                self.send_response("+OK Đăng nhập thành công")
            else:
                self.state = STATE_AUTH_USER
                self.send_response("-ERR Password không đúng")
        except Exception as e:
            print(f"Lỗi handle_pass: {e}")
            traceback.print_exc()
            self.state = STATE_AUTH_USER
            self.send_response("-ERR Lỗi server")

    def load_mailbox(self):
        """Load mail từ DB vào bộ nhớ cho session này"""
        try:
            db = SessionLocal()
            self.mailbox = db.query(ReceivedEmail).filter(
                ReceivedEmail.recipient_email == self.user_email
            ).order_by(ReceivedEmail.timestamp).all()
            db.close()
            self.marked_for_deletion = set()
            print(f"Đã load {len(self.mailbox)} email cho {self.user_email}")
        except Exception as e:
            print(f"Lỗi load_mailbox: {e}")
            traceback.print_exc()
            self.mailbox = []

    def handle_stat(self):
        try:
            count = len(self.mailbox)
            total_size = sum(len(m.raw_message.encode('utf-8') if isinstance(m.raw_message, str) else m.raw_message) for m in self.mailbox)
            self.send_response(f"+OK {count} {total_size}")
        except Exception as e:
            print(f"Lỗi handle_stat: {e}")
            self.send_response("-ERR Lỗi server")

    def handle_list(self):
        try:
            count = len(self.mailbox)
            total_size = sum(len(m.raw_message.encode('utf-8') if isinstance(m.raw_message, str) else m.raw_message) for m in self.mailbox)
            self.send_response(f"+OK {count} tin nhắn ({total_size} bytes)")
            for i, msg in enumerate(self.mailbox):
                if i + 1 not in self.marked_for_deletion:
                    msg_size = len(msg.raw_message.encode('utf-8') if isinstance(msg.raw_message, str) else msg.raw_message)
                    self.send_response(f"{i + 1} {msg_size}")
            self.send_response(".")
        except Exception as e:
            print(f"Lỗi handle_list: {e}")
            traceback.print_exc()
            self.send_response("-ERR Lỗi server")

    def unfold_headers(self, message_text):
        """
        Unfold MIME headers: Ghép các dòng header bị wrap lại với nhau
        Theo RFC 2822, dòng tiếp theo bắt đầu bằng whitespace là phần tiếp của header
        """
        lines = message_text.split('\n')
        unfolded_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i].rstrip('\r')
            
            # Nếu đang ở phần header (trước dòng trống đầu tiên)
            # và dòng tiếp theo bắt đầu bằng space/tab, ghép vào
            if ':' in line or (unfolded_lines and not unfolded_lines[-1].strip()):
                # Ghép các dòng continuation
                while i + 1 < len(lines) and lines[i + 1] and lines[i + 1][0] in (' ', '\t'):
                    i += 1
                    # Thay thế whitespace đầu dòng bằng 1 space
                    line += ' ' + lines[i].lstrip().rstrip('\r')
            
            unfolded_lines.append(line)
            i += 1
        
        return '\r\n'.join(unfolded_lines)

    def handle_retr(self, msg_id):
        try:
            msg_num = int(msg_id)
            
            if msg_num < 1 or msg_num > len(self.mailbox):
                self.send_response("-ERR Không có tin nhắn như vậy")
                return
                
            if msg_num in self.marked_for_deletion:
                self.send_response("-ERR Tin nhắn đã bị đánh dấu xóa")
                return
            
            msg = self.mailbox[msg_num - 1]
            msg_data = msg.raw_message
            
            # Đảm bảo msg_data là string
            if isinstance(msg_data, bytes):
                try:
                    msg_data = msg_data.decode('utf-8')
                except UnicodeDecodeError:
                    msg_data = msg_data.decode('latin-1', errors='replace')
            
            # DEBUG: In ra email gốc
            print("=" * 80)
            print("RAW EMAIL TRƯỚC KHI UNFOLD (first 800 chars):")
            print(msg_data[:800])
            print("=" * 80)
            
            # CRITICAL FIX: Unfold headers trước khi gửi
            try:
                msg_data = self.unfold_headers(msg_data)
                print(f"✓ Đã unfold headers cho email {msg_num}")
                
                # DEBUG: In ra email sau unfold
                print("=" * 80)
                print("EMAIL SAU KHI UNFOLD (first 800 chars):")
                print(msg_data[:800])
                print("=" * 80)
            except Exception as e:
                print(f"⚠ Không thể unfold headers: {e}")
                # Nếu unfold lỗi, tiếp tục với data gốc
            
            # Tính size chính xác
            msg_bytes = msg_data.encode('utf-8', errors='replace')
            print(f"Gửi email {msg_num}: {len(msg_bytes)} bytes")
            
            self.send_response(f"+OK {len(msg_bytes)} octets")
            
            # Gửi từng dòng
            lines = msg_data.split('\r\n')
            
            for idx, line in enumerate(lines):
                try:
                    # POP3 byte-stuffing: nếu dòng bắt đầu bằng '.', thêm '.'
                    if line.startswith('.'):
                        line = '.' + line
                    
                    self.request.sendall(f"{line}\r\n".encode('utf-8', errors='replace'))
                    
                except Exception as e:
                    print(f"Lỗi khi gửi dòng {idx}: {e}")
                    raise
            
            # Kết thúc message
            self.send_response(".")
            print(f"✓ Đã gửi xong email {msg_num}")
            
        except ValueError:
            self.send_response("-ERR ID tin nhắn phải là số")
        except Exception as e:
            print(f"Lỗi handle_retr: {e}")
            traceback.print_exc()
            try:
                self.send_response("-ERR Lỗi server khi lấy tin nhắn")
            except:
                pass

    def handle_dele(self, msg_id):
        try:
            msg_num = int(msg_id)
            if 1 <= msg_num <= len(self.mailbox) and msg_num not in self.marked_for_deletion:
                self.marked_for_deletion.add(msg_num)
                self.send_response(f"+OK Tin nhắn {msg_num} đã xoá")
            else:
                self.send_response("-ERR Không có tin nhắn như vậy")
        except ValueError:
            self.send_response("-ERR ID tin nhắn phải là số")
        except Exception as e:
            print(f"Lỗi handle_dele: {e}")
            self.send_response("-ERR Lỗi server")

    def handle_rset(self):
        try:
            self.marked_for_deletion.clear()
            self.send_response("+OK")
        except Exception as e:
            print(f"Lỗi handle_rset: {e}")
            self.send_response("-ERR Lỗi server")
        
    def handle_quit(self):
        try:
            if self.state == STATE_TRANSACTION:
                db = SessionLocal()
                try:
                    # Xóa các email đã đánh dấu
                    for msg_num in self.marked_for_deletion:
                        msg_db_id = self.mailbox[msg_num - 1].id
                        db.query(ReceivedEmail).filter(ReceivedEmail.id == msg_db_id).delete()
                    db.commit()
                    self.send_response("+OK Tạm biệt")
                except Exception as e:
                    print(f"Lỗi khi xoá mail: {e}")
                    traceback.print_exc()
                    db.rollback()
                    self.send_response("-ERR Lỗi server khi xoá mail")
                finally:
                    db.close()
            else:
                self.send_response("+OK Tạm biệt")
        except Exception as e:
            print(f"Lỗi handle_quit: {e}")
            traceback.print_exc()

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

def run_pop3_server():
    HOST, PORT = "localhost", 110
    print(f"POP3 Server đang chạy ở {HOST}:{PORT}...")
    try:
        server = ThreadedTCPServer((HOST, PORT), POP3Handler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTắt server...")
        server.shutdown()
    except Exception as e:
        print(f"Lỗi server: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    run_pop3_server()