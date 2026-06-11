import os
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger("SecurityModule")

# A .env file reader since python-dotenv might not be installed
def get_or_create_app_key():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    secret_key = None
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("APP_SECRET_KEY="):
                    secret_key = line.strip().split("=", 1)[1]
                    break
    
    if not secret_key:
        secret_key = Fernet.generate_key().decode()
        with open(env_path, "a") as f:
            f.write(f"\nAPP_SECRET_KEY={secret_key}\n")
        logger.info("Generated new APP_SECRET_KEY and saved to .env")
        
    return secret_key

_FERNET = Fernet(get_or_create_app_key().encode())

def encrypt_secret(secret: str) -> str:
    """Encrypts a string (e.g. TOTP secret) for safe database storage."""
    return _FERNET.encrypt(secret.encode()).decode()

def decrypt_secret(encrypted_secret: str) -> str:
    """Decrypts a string from database storage."""
    return _FERNET.decrypt(encrypted_secret.encode()).decode()
