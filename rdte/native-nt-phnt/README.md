# R1 native NT object introspection (read-only synthetic)

Purpose: empirically qualify original Windows NT process/handle query primitives using the exact open-source phnt headers reused by System Informer. This is a source-level discovery / genuine Windows hosted runtime proof, NOT WinBot runtime integration, Wine introspection or original-target RE.

Upstream: winsiderss/phnt 53fbbdc5b5d2b08761db1c7b26bfa8c820924356 (MIT; reviewed source separately). Windows-2022 public runner and MSVC/Windows SDK. The only target is the probe's own process and a freshly created unnamed event handle.

First check: NtQueryInformationProcess(ProcessBasicInformation) yields self PID and non-null PEB pointer. Second check: NtQueryObject(ObjectTypeInformation) reports the created object's Event type. The PEB pointer and returned object structures stay inside the running process; no arbitrary memory is read, no raw pointers appear in logs, and no system/other-user objects are enumerated.

Do not equate PHNT type definitions with observed object creation, or user-mode NT query with kernel-wide truth. Unknown/denied access and Windows build differences are separate follow-on negative tests.

Release boundary: synthetic RDTE only, run on free-tier public windows hosted GitHub Actions. WinBot native Windows integration belongs to mark-e-deyoung/WinBot; Ghidra/Observatory to mark-e-deyoung/ghidra-tools#4 with its existing R030/R126/H0 restrictions. No protected branch, image, private target or kernel driver modifications.
