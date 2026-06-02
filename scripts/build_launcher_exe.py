import os
import sys
import subprocess
import shutil
import time

def build():
    project_root = os.getcwd()
    
    # 1. Build Frontend
    print("=== Step 1: Building Frontend ===")
    frontend_dir = os.path.join(project_root, "frontend")
    if os.path.exists(frontend_dir):
        os.chdir(frontend_dir)
        try:
            subprocess.run(["npm", "install"], shell=True, check=True)
            subprocess.run(["npm", "run", "build"], shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Frontend build failed: {e}")
            return
        os.chdir(project_root)
    else:
        print("Frontend directory not found. Skipping frontend build.")

    # 2. Prepare PyInstaller Command
    print("\n=== Step 2: Building EXE with PyInstaller ===")
    
    # Kill any existing instance to avoid PermissionError
    if os.name == 'nt':
        print("Ensuring no existing instances of AradhanaPaymentAuditor.exe are running...")
        subprocess.run(['taskkill', '/F', '/IM', 'AradhanaPaymentAuditor.exe'], capture_output=True)
        time.sleep(2) # Give it a moment to release file handles
    
    # Ensure pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # Assets to bundle
    # Format: (source, destination)
    add_data = [
        ("backend", "backend"),
        ("launcher_config.json", "."),
        (".env.example", "."),
        ("frontend/dist", "frontend/dist")
    ]
    
    data_args = []
    for src, dst in add_data:
        if os.path.exists(src):
            data_args.extend(["--add-data", f"{src};{dst}"])
        else:
            print(f"Warning: Asset not found: {src}")

    # Build command
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed", # No console window for the launcher
        "--name", "AradhanaPaymentAuditor",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "imaplib",
        "--hidden-import", "ssl",
        "--hidden-import", "socket",
        "--hidden-import", "email",
        "--hidden-import", "email.message",
        "--hidden-import", "email.header",
        "--hidden-import", "email.utils",
        "--hidden-import", "email.parser",
        "--hidden-import", "email.policy",
        "--hidden-import", "email.mime.text",
        "--hidden-import", "email.mime.multipart",
        "--hidden-import", "email.mime.base",
        "--hidden-import", "email.encoders",
        "--hidden-import", "smtplib",
        "--hidden-import", "sqlite3",
        "--hidden-import", "pathlib",
        "--hidden-import", "threading",
        "--hidden-import", "multiprocessing",
        "--hidden-import", "subprocess",
        "--hidden-import", "signal",
        "--hidden-import", "quopri",
        "--hidden-import", "base64",
        "--hidden-import", "datetime",
        "--hidden-import", "decimal",
        "--collect-all", "pydantic",
        "--collect-all", "pydantic_core",
        "--collect-all", "annotated_types",
        "--collect-all", "typing_extensions",
        "--collect-all", "typing_inspection",
        "--collect-all", "fastapi",
        "--collect-all", "starlette",
        "--collect-all", "sqlalchemy",
        "--collect-all", "watchdog",
        "--collect-all", "dotenv",
        "--collect-all", "pdfplumber",
        "--collect-all", "pdfminer",
        "--collect-all", "pdfminer.six",
        "--collect-all", "PIL",
        "--collect-all", "pypdfium2",
        "--collect-all", "charset_normalizer",
        "--collect-all", "cryptography",
        "--collect-all", "cffi",
    ]
    
    cmd.extend(data_args)
    cmd.append("scripts/launcher.py")

    print(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        exe_path = os.path.join(project_root, 'dist', 'AradhanaPaymentAuditor.exe')
        print(f"\n=== Build Success! EXE at: {exe_path} ===")
        
        # 3. Post-Build Self-Test
        print("\n=== Step 3: Running Post-Build Self-Test ===")
        test_res = subprocess.run([exe_path, "--self-test"], capture_output=True, text=True)
        print(test_res.stdout)
        if test_res.returncode == 0:
            print("✓ Post-build self-test passed!")
            print(f"Final EXE Size: {os.path.getsize(exe_path) / (1024*1024):.2f} MB")
        else:
            print("❌ Post-build self-test failed!")
            print(test_res.stderr)
            sys.exit(1)

    except subprocess.CalledProcessError as e:
        print(f"PyInstaller build failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build()
