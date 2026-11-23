// SPDX-License-Identifier: MIT
// Synthetic two-process metadata-only Windows observer.
// Queries only a child created by this test, no driver, privileges or injection.
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <cstdint>
#include <cwchar>
#include <cstdio>

struct Shared {
    DWORD pid;
    ULONGLONG base;
    SIZE_T length;
};

static HANDLE from_arg(const wchar_t* text)
{
    wchar_t* end = nullptr;
    const unsigned long long n = _wcstoui64(text, &end, 10);
    if (!text[0] || !end || *end || !n) return nullptr;
    return reinterpret_cast<HANDLE>(static_cast<ULONG_PTR>(n));
}

static int child_main(const wchar_t* mapping_arg, const wchar_t* ready_arg,
                      const wchar_t* release_arg)
{
    const HANDLE map = from_arg(mapping_arg);
    const HANDLE ready = from_arg(ready_arg);
    const HANDLE release = from_arg(release_arg);
    if (!map || !ready || !release) return 10;
    auto* state = static_cast<Shared*>(
        MapViewOfFile(map, FILE_MAP_WRITE, 0, 0, sizeof(Shared)));
    if (!state) return 11;
    void* block = VirtualAlloc(nullptr, 8192,
                              MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (!block) return 12;

    state->pid = GetCurrentProcessId();
    state->base = static_cast<ULONGLONG>(reinterpret_cast<ULONG_PTR>(block));
    state->length = 8192;
    const BOOL sent = SetEvent(ready);
    const DWORD wait = WaitForSingleObject(release, 15000);
    const BOOL freed = VirtualFree(block, 0, MEM_RELEASE);
    UnmapViewOfFile(state);
    return sent && wait == WAIT_OBJECT_0 && freed ? 0 : 13;
}

static int parent_main()
{
    SECURITY_ATTRIBUTES inherit = {};
    inherit.nLength = sizeof(inherit);
    inherit.bInheritHandle = TRUE;
    HANDLE map = CreateFileMappingW(INVALID_HANDLE_VALUE, &inherit,
                                    PAGE_READWRITE, 0, 4096, nullptr);
    HANDLE ready = CreateEventW(&inherit, TRUE, FALSE, nullptr);
    HANDLE release = CreateEventW(&inherit, TRUE, FALSE, nullptr);
    if (!map || !ready || !release) return 20;
    auto* state = static_cast<Shared*>(
        MapViewOfFile(map, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(Shared)));
    if (!state) return 21;
    state->pid = 0;
    state->base = 0;
    state->length = 0;

    wchar_t filename[MAX_PATH] = {};
    const DWORD count = GetModuleFileNameW(nullptr, filename, MAX_PATH);
    if (!count || count >= MAX_PATH) return 22;

    wchar_t args[2048] = {};
    const int written = swprintf(args, sizeof(args) / sizeof(args[0]),
        L"\"%ls\" --child %llu %llu %llu", filename,
        static_cast<unsigned long long>(reinterpret_cast<ULONG_PTR>(map)),
        static_cast<unsigned long long>(reinterpret_cast<ULONG_PTR>(ready)),
        static_cast<unsigned long long>(reinterpret_cast<ULONG_PTR>(release)));
    if (written <= 0 || written >= static_cast<int>(sizeof(args) / sizeof(args[0])))
        return 23;

    STARTUPINFOW startup = {};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process = {};
    if (!CreateProcessW(filename, args, nullptr, nullptr, TRUE,
                        CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process))
        return 24;

    int status = 0;
    const DWORD announced = WaitForSingleObject(ready, 15000);
    if (announced != WAIT_OBJECT_0) {
        status = 25;
    } else if (state->pid != process.dwProcessId || !state->base ||
               state->length != 8192) {
        status = 26;
    } else {
        MEMORY_BASIC_INFORMATION region = {};
        const void* address = reinterpret_cast<const void*>(
            static_cast<ULONG_PTR>(state->base));
        if (VirtualQueryEx(process.hProcess, address, &region,
                           sizeof(region)) != sizeof(region) ||
            region.State != MEM_COMMIT ||
            region.Protect != PAGE_READWRITE ||
            region.BaseAddress != address || region.RegionSize < state->length) {
            status = 27;
        }

        HMODULE module = nullptr;
        DWORD needed = 0;
        MODULEINFO image = {};
        if (!EnumProcessModules(process.hProcess, &module, sizeof(module),
                                &needed) || needed < sizeof(module) || !module ||
            !GetModuleInformation(process.hProcess, module, &image,
                                  sizeof(image)) || image.SizeOfImage < 4096 ||
            image.lpBaseOfDll != module) {
            status = 28;
        }
    }

    SetEvent(release);
    const DWORD stopped = WaitForSingleObject(process.hProcess, 15000);
    DWORD exit_code = 0;
    if (stopped != WAIT_OBJECT_0 ||
        !GetExitCodeProcess(process.hProcess, &exit_code) || exit_code != 0)
        status = 29;
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    UnmapViewOfFile(state);
    CloseHandle(map);
    CloseHandle(ready);
    CloseHandle(release);
    if (status == 0)
        std::puts("PASS: metadata_only_remote_child_module_and_virtual_region");
    // No raw PID, module, path, handle, guest VA or application contents in logs.
    return status;
}

int wmain(int argc, wchar_t** argv)
{
    if (argc == 5 && wcscmp(argv[1], L"--child") == 0)
        return child_main(argv[2], argv[3], argv[4]);
    if (argc != 1) return 2;
    return parent_main();
}
