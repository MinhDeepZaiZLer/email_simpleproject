from smtpd import DebuggingServer
import asyncore

class CustomSMTPServer(DebuggingServer):
    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        print(f"📨 Mail from {mailfrom} to {rcpttos}")
        print(data)
        return

if __name__ == "__main__":
    print("SMTP server chạy ở cổng 1025...")
    server = CustomSMTPServer(('localhost', 1025), None)
    asyncore.loop()
