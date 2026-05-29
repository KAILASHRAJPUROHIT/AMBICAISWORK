import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import threading

import worker

class PrintAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AradhanaPrintAgent"
    _svc_display_name_ = "Aradhana Print Agent"
    _svc_description_ = "Background service that downloads and prints jobs for Aradhana Jewellers."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)
        self.is_alive = True

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_alive = False

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()

    def main(self):
        # Run worker in a separate thread so we can listen to the stop event
        worker_thread = threading.Thread(target=self._run_worker, daemon=True)
        worker_thread.start()
        
        # Wait for service stop signal
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

    def _run_worker(self):
        worker.local_db.init_db()
        while self.is_alive:
            worker.run_once()
            # Sleep in small increments to allow responsive shutdown
            for _ in range(worker.POLL_INTERVAL * 2):
                if not self.is_alive:
                    break
                import time
                time.sleep(0.5)

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PrintAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PrintAgentService)
