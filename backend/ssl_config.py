import os
import subprocess

def generate_self_signed_cert():
    cert_dir = "certs"
    os.makedirs(cert_dir, exist_ok=True)
    
    key_path = os.path.join(cert_dir, "key.pem")
    cert_path = os.path.join(cert_dir, "cert.pem")
    
    if os.path.exists(key_path) and os.path.exists(cert_path):
        return key_path, cert_path

    # Generate using openssl if available
    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:4096", "-keyout", key_path,
            "-out", cert_path, "-days", "365", "-nodes",
            "-subj", "/C=IN/ST=Karnataka/L=Bangalore/O=Aradhana/CN=aradhana-auditor.local"
        ], check=True)
    except Exception as e:
        print(f"Error generating cert: {e}. Please install OpenSSL.")
        return None, None
        
    return key_path, cert_path
