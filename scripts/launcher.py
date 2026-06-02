import os
import sys
import subprocess
import time
import json
import signal
import logging
import webbrowser
import socket
import argparse
import multiprocessing
from pathlib import Path

# Configure logging
LOG_DIR = r"C:\Aradhana\PaymentAuditor\Logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "launcher.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Launcher")

class AradhanaLauncher:
    def __init__(self, config_path="launcher_config.json"):
        self.config_path = config_path
        self.config = self.load_config()
        self.backend_process = None
        self.running = True

    def load_config(self):
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {
                "backend_host": "127.0.0.1",
                "backend_port": 8000,
                "auto_open_browser": True
            }

    def is_port_in_use(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((self.config["backend_host"], port)) == 0

    def start_backend(self):
        port = self.config["backend_port"]
        if self.is_port_in_use(port):
            logger.warning(f"Port {port} already in use. Attempting to reuse...")
            return True

        logger.info("Starting Backend API...")
        
        # In a frozen app (EXE), sys.executable is the EXE. 
        # We call ourselves with --backend-internal to start the API.
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, "--backend-internal"]
        else:
            cmd = [sys.executable, os.path.abspath(__file__), "--backend-internal"]
        
        # Hide window on Windows
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            self.backend_process = subprocess.Popen(
                cmd, 
                cwd=os.getcwd(),
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            logger.info(f"Backend started with PID: {self.backend_process.pid}")
            return True
        except Exception as e:
            logger.error(f"Failed to start backend: {e}")
            return False

    def wait_for_backend(self, timeout=30):
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_port_in_use(self.config["backend_port"]):
                logger.info("Backend is ready.")
                return True
            time.sleep(1)
        logger.error("Backend failed to start within timeout.")
        return False

    def open_browser(self):
        if self.config.get("auto_open_browser", True):
            url = f"http://{self.config['backend_host']}:{self.config['backend_port']}"
            logger.info(f"Opening browser to {url}")
            webbrowser.open(url)

    def stop_all(self):
        self.running = False
        if self.backend_process:
            logger.info(f"Stopping backend process {self.backend_process.pid}...")
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.backend_process.pid)], capture_output=True)
            else:
                self.backend_process.terminate()
            self.backend_process = None
        logger.info("All processes stopped.")

    def run(self):
        if not self.start_backend():
            return

        if self.wait_for_backend():
            self.open_browser()
            try:
                while self.running:
                    if self.backend_process and self.backend_process.poll() is not None:
                        logger.error("Backend process crashed. Restarting...")
                        self.start_backend()
                    time.sleep(5)
            except (KeyboardInterrupt, SystemExit):
                self.stop_all()

    def install_startup(self):
        if os.name != 'nt':
            print("Startup installation only supported on Windows.")
            return
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            startup_path = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            shortcut_path = startup_path / "AradhanaPaymentAuditor.lnk"
            target = sys.executable
            arguments = ""
            if not getattr(sys, 'frozen', False):
                arguments = os.path.abspath(__file__)
            shortcut = shell.CreateShortCut(str(shortcut_path))
            shortcut.Targetpath = target
            shortcut.Arguments = arguments
            shortcut.WorkingDirectory = os.getcwd()
            shortcut.IconLocation = target
            shortcut.save()
            logger.info(f"Startup shortcut created at {shortcut_path}")
            print(f"Successfully installed to startup: {shortcut_path}")
        except ImportError:
            logger.error("pywin32 not installed. Cannot create shortcut automatically.")
            print("Error: pywin32 library is required for this action. Run: pip install pywin32")
        except Exception as e:
            logger.error(f"Failed to install startup: {e}")
            print(f"Failed to install startup: {e}")

    def remove_startup(self):
        if os.name != 'nt': return
        startup_path = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        shortcut_path = startup_path / "AradhanaPaymentAuditor.lnk"
        if shortcut_path.exists():
            shortcut_path.unlink()
            logger.info(f"Startup shortcut removed from {shortcut_path}")
            print(f"Successfully removed from startup: {shortcut_path}")
        else:
            print("Startup shortcut not found.")

def run_backend_internal():
    import uvicorn
    sys.path.insert(0, os.getcwd())
    from backend.review_api import app
    config = AradhanaLauncher().load_config()
    cert_path = r"C:\Aradhana\SSL\cert.pem"
    key_path = r"C:\Aradhana\SSL\key.pem"
    if os.path.exists(cert_path) and os.path.exists(key_path):
        uvicorn.run(app, host=config["backend_host"], port=config["backend_port"], ssl_keyfile=key_path, ssl_certfile=cert_path)
    else:
        uvicorn.run(app, host=config["backend_host"], port=config["backend_port"])

def run_self_test():
    print("=== Aradhana Payment Auditor Self-Test ===")
    try:
        import pydantic
        print(f"OK: Pydantic imported (version: {pydantic.__version__})")
        import fastapi
        print(f"OK: FastAPI imported (version: {fastapi.__version__})")
        import uvicorn
        print(f"OK: Uvicorn imported (version: {uvicorn.__version__})")
        import sqlalchemy
        print(f"OK: SQLAlchemy imported (version: {sqlalchemy.__version__})")
        import watchdog
        print("OK: Watchdog imported")
        import dotenv
        print("OK: Dotenv imported")
        
        sys.path.insert(0, os.getcwd())
        from backend.database import SessionLocal
        db = SessionLocal()
        db.close()
        print("OK: Database connection initialized")
        
        config = AradhanaLauncher().load_config()
        print(f"OK: Config loaded: {config.get('backend_host')}:{config.get('backend_port')}")
        
        print("\nSELF-TEST PASSED SUCCESSFULLY")
        return True
    except Exception as e:
        print(f"\nSELF-TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Aradhana Payment Auditor Launcher")
    parser.add_argument("--install-startup", action="store_true", help="Install to Windows Startup")
    parser.add_argument("--remove-startup", action="store_true", help="Remove from Windows Startup")
    parser.add_argument("--self-test", action="store_true", help="Verify dependencies and environment")
    parser.add_argument("--backend-internal", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    
    if args.self_test:
        success = run_self_test()
        sys.exit(0 if success else 1)
        
    if args.backend_internal:
        run_backend_internal()
        sys.exit(0)
    launcher = AradhanaLauncher()
    if args.install_startup:
        launcher.install_startup()
    elif args.remove_startup:
        launcher.remove_startup()
    else:
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}. Shutting down...")
            launcher.stop_all()
            sys.exit(0)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        launcher.run()
