import os
import sys
import subprocess
import shutil

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
    
    # Ensure pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # Assets to bundle
    # Format: "source;dest" (Windows uses ;)
    add_data = [
        ("backend;backend"),
        ("launcher_config.json;."),
        (".env.example;."),
        ("frontend/dist;frontend/dist")
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
    ]
    
    cmd.extend(data_args)
    cmd.append("scripts/launcher.py")

    print(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        print("\n=== Success! ===")
        print(f"EXE created at: {os.path.join(project_root, 'dist', 'AradhanaPaymentAuditor.exe')}")
    except subprocess.CalledProcessError as e:
        print(f"PyInstaller build failed: {e}")

if __name__ == "__main__":
    build()
