# Prime Extraction Runtime Requirements

> **Local edge only:** These requirements apply to the optional Windows Prime automation agent, not the hosted FastAPI service. The absolute path below is historical and must be replaced by a tenant-specific configured interpreter path.

## 1. Requirement: 32-bit Python
To reliably automate and extract data from the 32-bit Prime VB6 application (`FA.exe`), the extraction engine **MUST** run on a 32-bit Python interpreter. 

Using 64-bit Python results in "control blindness" where MDI child forms and internal textboxes are invisible to the Windows automation backend.

### Standardized Path
The verified runtime is located at:
`C:\Aradhana\venv32\Scripts\python.exe`

## 2. Dependencies
- **pywinauto**: Must use the `win32` backend.
- **psutil**: For process architecture verification.
- **pypiwin32**: For lower-level COM/Win32 interactions if needed.

## 3. Runtime Validation
All Prime extraction scripts (`prime_invoice_extractor.py`, etc.) now include a mandatory bitness check at startup. If executed under a 64-bit interpreter, they will exit with a `BITNESS_MISMATCH` error.
