# Prime Control Access Diagnostic Report

**Date:** 2026-05-31
**Environment:** Python 64-bit, FA.exe 32-bit

## 1. Environment Analysis
| Component | Value |
|-----------|-------|
| Python Arch | 64-bit |
| FA.exe Arch | 32-bit |
| **Bitness Mismatch** | **YES** |
| OS Platform | Windows 10 |
| pywinauto Backend | win32 |

## 2. Hierarchy Analysis (MDI Probe)
- **MDI Parent Window:** Found (`SHREE ARADHANA JEWELLERS`)
- **MDIClient Area:** Found
- **MDI Child Forms:** **NOT FOUND**

The `pywinauto` `win32` backend, when running in a 64-bit process, failed to enumerate the 32-bit child windows of the `MDIClient`. This is a classic symptom of bitness-induced "control blindness."

## 3. Conclusions

### Likely bitness issue? **YES**
The confirmed mismatch between 64-bit Python and 32-bit Prime (`FA.exe`) is the primary blocker. The automation backend cannot reliably traverse the internal window tree of a 32-bit MDI application from a 64-bit process.

### Likely MDI issue? **YES**
VB6's MDI implementation adds a layer of complexity. The `MDIClient` acts as a container that often hides children from standard cross-process enumeration when bitness doesn't match.

### Likely extraction logic issue? **NO**
The pattern-matching and spatial-grouping logic is technically sound but has no "material" to work with because the control tree is truncated at the MDI boundary.

## 4. Recommendation
**Transition to 32-bit Python environment.**
To reliably automate and extract data from the 32-bit Prime VB6 application, the auditor's extraction engine must run on a 32-bit Python interpreter. This will align the address spaces and allow standard Win32 APIs to "see" the full control hierarchy.
