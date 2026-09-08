import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import threading

import agent

class PrintAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AradhanaPrintAgent"
    _svc_display_name_ = "Aradhana Print Agent"
    _svc_description_ = "Background service that downloads and prints jobs for Aradhana Jewellers."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self.main()

    def main(self):
        # agent.main_loop() runs forever; daemon=True means it dies when service exits
        agent_thread = threading.Thread(target=self._run_agent, daemon=True)
        agent_thread.start()
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

    def _run_agent(self):
        agent.setup_logging()
        agent.validate_config()
        agent.main_loop()

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PrintAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PrintAgentService)
