from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
import os
import json
import base64

# --- Quản lý Key RSA ---
def generate_rsa_keys():
    """Tạo cặp Public/Private Key RSA"""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key = private_key.public_key()
    
    pem_priv = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    pem_pub = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return pem_pub.decode('utf-8'), pem_priv.decode('utf-8')

def load_public_key(pem_pub_data):
    return serialization.load_pem_public_key(pem_pub_data.encode('utf-8'), backend=default_backend())

def load_private_key(pem_priv_data):
    return serialization.load_pem_private_key(pem_priv_data.encode('utf-8'), password=None, backend=default_backend())

# --- Chữ ký số ---
def sign_message(message_str, private_key_pem):
    """Tạo chữ ký số"""
    private_key = load_private_key(private_key_pem)
    message_bytes = message_str.encode('utf-8')
    
    signature = private_key.sign(
        message_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    # Trả về Base64 an toàn (không có ký tự đặc biệt)
    return base64.b64encode(signature).decode('utf-8')

def verify_signature(message_str, signature_b64, public_key_pem):
    """Xác thực chữ ký"""
    public_key = load_public_key(public_key_pem)
    message_bytes = message_str.encode('utf-8')
    signature_bytes = base64.b64decode(signature_b64)
    
    try:
        public_key.verify(
            signature_bytes,
            message_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except Exception:
        return False

# --- Mã hóa Hybrid (AES + RSA) ---
def encrypt_email_body(body_str, recipient_public_key_pem):
    """Mã hóa nội dung email"""
    public_key = load_public_key(recipient_public_key_pem)
    
    # 1. Tạo key AES ngẫu nhiên
    aes_key = os.urandom(32)
    iv = os.urandom(16)
    
    # 2. Mã hóa body bằng AES
    aes_algorithm = algorithms.AES(aes_key)
    cipher_aes = Cipher(aes_algorithm, modes.CBC(iv), backend=default_backend())
    encryptor = cipher_aes.encryptor()
    
    padder = sym_padding.PKCS7(aes_algorithm.block_size).padder()
    padded_data = padder.update(body_str.encode('utf-8')) + padder.finalize()
    encrypted_body = encryptor.update(padded_data) + encryptor.finalize()
    
    # 3. Mã hóa key AES bằng RSA
    encrypted_aes_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    # 4. Trả về Base64 (an toàn cho email)
    return base64.b64encode(encrypted_aes_key).decode('utf-8'), \
           base64.b64encode(iv).decode('utf-8'), \
           base64.b64encode(encrypted_body).decode('utf-8')

def decrypt_email_body(encrypted_key_b64, iv_b64, encrypted_body_b64, recipient_private_key_pem):
    """Giải mã nội dung email"""
    private_key = load_private_key(recipient_private_key_pem)
    
    # 1. Decode Base64
    encrypted_aes_key = base64.b64decode(encrypted_key_b64)
    iv = base64.b64decode(iv_b64)
    encrypted_body = base64.b64decode(encrypted_body_b64)
    
    # 2. Giải mã key AES bằng RSA
    aes_key = private_key.decrypt(
        encrypted_aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    # 3. Giải mã body bằng AES
    aes_algorithm = algorithms.AES(aes_key)
    cipher_aes = Cipher(aes_algorithm, modes.CBC(iv), backend=default_backend())
    decryptor = cipher_aes.decryptor()
    padded_decrypted_data = decryptor.update(encrypted_body) + decryptor.finalize()
    
    # 4. Unpad
    unpadder = sym_padding.PKCS7(aes_algorithm.block_size).unpadder()
    decrypted_data = unpadder.update(padded_decrypted_data) + unpadder.finalize()
    
    return decrypted_data.decode('utf-8')

# --- Package/Unpackage cho Email Body ---
def package_encrypted_email(body_plaintext, sender_private_key_pem, recipient_public_key_pem):
    """
    Đóng gói email: mã hóa body + ký
    Trả về: JSON string để đặt vào email body
    """
    # 1. Ký nội dung gốc
    signature = sign_message(body_plaintext, sender_private_key_pem)
    
    # 2. Mã hóa nội dung
    enc_key, iv, enc_body = encrypt_email_body(body_plaintext, recipient_public_key_pem)
    
    # 3. Đóng gói thành JSON
    package = {
        "version": "1.0",
        "encrypted_key": enc_key,
        "iv": iv,
        "encrypted_body": enc_body,
        "signature": signature
    }
    
    # Trả về JSON string (an toàn cho email body)
    return json.dumps(package, indent=2)

def unpackage_encrypted_email(json_body, recipient_private_key_pem, sender_public_key_pem):
    """
    Giải mã và xác thực email
    Trả về: (decrypted_body, is_verified)
    """
    try:
        # 1. Parse JSON
        package = json.loads(json_body)
        
        # 2. Giải mã body
        decrypted_body = decrypt_email_body(
            package["encrypted_key"],
            package["iv"],
            package["encrypted_body"],
            recipient_private_key_pem
        )
        
        # 3. Xác thực chữ ký
        is_verified = verify_signature(
            decrypted_body,
            package["signature"],
            sender_public_key_pem
        )
        
        return decrypted_body, is_verified
        
    except Exception as e:
        raise Exception(f"Lỗi giải mã email: {e}")