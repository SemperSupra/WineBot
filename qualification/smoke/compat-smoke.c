/* Synthetic Win32 PE test application; no C runtime and no private input. */
typedef void *HANDLE;
typedef unsigned long DWORD;
typedef int BOOL;

__declspec(dllimport) HANDLE __stdcall CreateFileA(
    const char *, DWORD, DWORD, void *, DWORD, DWORD, HANDLE);
__declspec(dllimport) BOOL __stdcall WriteFile(
    HANDLE, const void *, DWORD, DWORD *, void *);
__declspec(dllimport) BOOL __stdcall ReadFile(
    HANDLE, void *, DWORD, DWORD *, void *);
__declspec(dllimport) BOOL __stdcall CloseHandle(HANDLE);
__declspec(dllimport) void __stdcall ExitProcess(DWORD);

static const char filename[] = "winebot_compat_synthetic.txt";
static const char content[] = "winebot-fixture-2026-10-25\n";

void mainCRTStartup(void) {
    DWORD count = 0;
    char readback[sizeof(content)] = {0};
    HANDLE file = CreateFileA(filename, 0x40000000u, 0, 0, 2, 0x80u, 0);
    if (file == (HANDLE)(-1)) ExitProcess(11);
    if (!WriteFile(file, content, (DWORD)(sizeof(content) - 1), &count, 0)
        || count != sizeof(content) - 1) ExitProcess(12);
    if (!CloseHandle(file)) ExitProcess(13);
    file = CreateFileA(filename, 0x80000000u, 1, 0, 3, 0x80u, 0);
    if (file == (HANDLE)(-1)) ExitProcess(14);
    count = 0;
    if (!ReadFile(file, readback, (DWORD)(sizeof(content) - 1), &count, 0)
        || count != sizeof(content) - 1) ExitProcess(15);
    if (!CloseHandle(file)) ExitProcess(16);
    for (unsigned int i = 0; i < sizeof(content) - 1; ++i) {
        if (readback[i] != content[i]) ExitProcess(17);
    }
    ExitProcess(0);
}
