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

def get_project_root():
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.basename(exe_dir).lower() == 'dist':
            return os.path.dirname(exe_dir)
        return r"C:\Users\kaila\aradhana-payment-auditor\aradhana-payment-auditor"
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Force CWD and Python Path to Project Root immediately
ROOT_DIR = get_project_root()
os.chdir(ROOT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Configure logging
LOG_DIR = r"C:\Aradhana\PaymentAuditor\Logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "launcher.log")
BACKEND_LOG_FILE = os.path.join(LOG_DIR, "backend.log")

def redirect_streams():
    """Redirect stdout and stderr to files if they are None (windowed mode)."""
    try:
        if sys.stdout is None:
            sys.stdout = open(os.path.join(LOG_DIR, "launcher_stdout.log"), "a", encoding="utf-8", buffering=1)
        if sys.stderr is None:
            sys.stderr = open(os.path.join(LOG_DIR, "launcher_stderr.log"), "a", encoding="utf-8", buffering=1)
    except Exception:
        # Fallback to devnull if we can't open log files
        import os
        devnull = open(os.devnull, 'w')
        if sys.stdout is None: sys.stdout = devnull
        if sys.stderr is None: sys.stderr = devnull

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout if sys.stdout else sys.stderr)
    ]
)
logger = logging.getLogger("Launcher")

def log_environment():
    """Print critical path and environment diagnostics for debugging."""
    logger.info("=== Aradhana Launcher Environment ===")
    logger.info(f"Working Directory: {os.getcwd()}")
    logger.info(f"Executable: {sys.executable}")
    logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")
    
    env_path = os.path.join(os.getcwd(), ".env")
    logger.info(f"Expected .env path: {env_path} (Exists: {os.path.exists(env_path)})")
    
    db_path = os.path.join(os.getcwd(), "aradhana_dev.db")
    logger.info(f"Expected DB path: {db_path} (Exists: {os.path.exists(db_path)})")
    
    from backend.pdf_ingestion import WATCH_PATH
    logger.info(f"Invoice Share Path: {WATCH_PATH} (Exists: {os.path.exists(WATCH_PATH)})")
    logger.info("=====================================")

class AradhanaLauncher:
    def __init__(self, config_path="launcher_config.json"):
        log_environment()
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

    def free_port(self, port):
        if os.name == 'nt':
            try:
                # Find process using the port
                output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
                for line in output.splitlines():
                    if "LISTENING" in line:
                        parts = line.strip().split()
                        if len(parts) > 4:
                            pid = parts[-1]
                            # Only kill if it's our app (heuristic: python or Aradhana)
                            try:
                                tasklist = subprocess.check_output(f"tasklist /FI \"PID eq {pid}\" /NH", shell=True).decode().lower()
                                if "aradhana" in tasklist or "python" in tasklist:
                                    subprocess.run(f"taskkill /F /PID {pid} /T", shell=True, capture_output=True)
                                    logger.info(f"Freed port {port} by killing PID {pid} ({tasklist.strip()})")
                            except Exception:
                                pass
            except subprocess.CalledProcessError:
                pass

    def start_backend(self):
        port = self.config["backend_port"]
        if self.is_port_in_use(port):
            logger.warning(f"Port {port} in use. Attempting to free it...")
            self.free_port(port)
            time.sleep(2)
            if self.is_port_in_use(port):
                logger.error(f"Cannot free port {port}. Backend may fail to start.")

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
    import logging
    
    # Redirect streams if needed
    redirect_streams()
    
    # Manually configure logging for the backend process
    # StreamHandler requires a stream with .write(). If sys.stdout is devnull, it works.
    handlers = [logging.FileHandler(BACKEND_LOG_FILE)]
    if sys.stdout and hasattr(sys.stdout, 'write'):
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    sys.path.insert(0, os.getcwd())
    from backend.review_api import app
    config = AradhanaLauncher().load_config()
    
    # Check for SSL
    cert_path = r"C:\Aradhana\SSL\cert.pem"
    key_path = r"C:\Aradhana\SSL\key.pem"
    
    # MANDATE: Disable uvicorn default logging in frozen windowed EXE
    uvicorn_kwargs = {
        "app": app,
        "host": config["backend_host"],
        "port": config["backend_port"],
        "log_config": None, # Prevent uvicorn from configuring logging/isatty
        "access_log": False
    }
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        uvicorn_kwargs["ssl_keyfile"] = key_path
        uvicorn_kwargs["ssl_certfile"] = cert_path
        
    uvicorn.run(**uvicorn_kwargs)

def run_self_test():
    print("=== Aradhana Payment Auditor Self-Test ===")
    try:
        # Redirect streams for test context if in windowed mode
        redirect_streams()
        
        if sys.stdout is None or sys.stderr is None:
             raise RuntimeError("Standard streams are still None after redirection attempt")
             
        if not os.access(LOG_DIR, os.W_OK):
             raise RuntimeError(f"Log directory not writable: {LOG_DIR}")

        # Standard Library Imports
        import imaplib
        print("OK: imaplib imported")
        import ssl
        print("OK: ssl imported")
        import socket
        print("OK: socket imported")
        import email
        import email.message
        import email.header
        import email.utils
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        print("OK: email modules and MIME submodules imported")
        import smtplib
        print("OK: smtplib imported")
        import sqlite3
        print("OK: sqlite3 imported")
        import pathlib
        print("OK: pathlib imported")
        import threading
        print("OK: threading imported")
        import multiprocessing
        print("OK: multiprocessing imported")
        import subprocess
        print("OK: subprocess imported")
        import signal
        print("OK: signal imported")

        # Third Party Imports
        import pydantic
        print(f"OK: Pydantic imported (version: {pydantic.__version__})")
        import fastapi
        print(f"OK: FastAPI imported (version: {fastapi.__version__})")
        import uvicorn
        # Test uvicorn config initialization
        uvicorn.Config("backend.review_api:app")
        print(f"OK: Uvicorn imported and config validated")
        import sqlalchemy
        print(f"OK: SQLAlchemy imported (version: {sqlalchemy.__version__})")
        import watchdog
        print("OK: Watchdog imported")
        import dotenv
        print("OK: Dotenv imported")
        
        # PDF Parsing Dependencies
        import pdfplumber
        print(f"OK: pdfplumber imported (version: {pdfplumber.__version__})")
        import pdfminer
        print(f"OK: pdfminer imported (version: {pdfminer.__version__})")
        import PIL
        from PIL import Image
        print(f"OK: Pillow (PIL) imported (version: {PIL.__version__})")
        try:
            import pypdfium2
            print("OK: pypdfium2 imported")
        except ImportError:
            print("INFO: pypdfium2 not found (optional)")
            
        sys.path.insert(0, os.getcwd())
        from backend.database import SessionLocal
        db = SessionLocal()
        db.close()
        print("OK: Database connection initialized")
        
        # Verify backend imports
        from backend.pdf_ingestion import parse_pdf
        print("OK: Backend PDF ingestion module imported")
        from backend.email_poller import process_emails
        print("OK: Backend Email poller module imported")
        
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
    redirect_streams()
    
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
