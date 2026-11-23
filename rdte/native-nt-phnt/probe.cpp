// SPDX-License-Identifier: MIT
// Source-qualified native Windows NT API witness: synthetic-only, read-only.
// No driver, dump, process injection, or remote process enumeration.
#define PHNT_VERSION PHNT_WINDOWS_11
#define PHNT_MODE PHNT_MODE_USER
#include <phnt_windows.h>
#include <phnt.h>
#include <cwchar>
#include <cstdio>

int main()
{
    const DWORD pid = GetCurrentProcessId();
    PROCESS_BASIC_INFORMATION pbi = {};
    ULONG bytes = 0;
    const NTSTATUS pstatus = NtQueryInformationProcess(
        GetCurrentProcess(), ProcessBasicInformation, &pbi, sizeof(pbi), &bytes);
    if (!NT_SUCCESS(pstatus) || !pbi.PebBaseAddress ||
        static_cast<DWORD>(reinterpret_cast<ULONG_PTR>(pbi.UniqueProcessId)) != pid)
        return 10;

    HANDLE event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!event) return 11;

    alignas(void*) BYTE object_info[4096] = {};
    ULONG required = 0;
    const NTSTATUS ostatus = NtQueryObject(
        event, ObjectTypeInformation, object_info, sizeof(object_info), &required);
    CloseHandle(event);
    if (!NT_SUCCESS(ostatus)) return 12;

    const auto* type_info =
        reinterpret_cast<const OBJECT_TYPE_INFORMATION*>(object_info);
    if (!type_info->TypeName.Buffer ||
        type_info->TypeName.Length != 5 * sizeof(wchar_t) ||
        wcsncmp(type_info->TypeName.Buffer, L"Event", 5) != 0)
        return 13;

    // Independent read-only native NT thread query. A thread ID and TEB
    // location are runtime-known anchors; no thread memory is exported.
    THREAD_BASIC_INFORMATION thread_info = {};
    ULONG thread_bytes = 0;
    const NTSTATUS tstatus = NtQueryInformationThread(
        GetCurrentThread(), ThreadBasicInformation, &thread_info,
        sizeof(thread_info), &thread_bytes);
    if (!NT_SUCCESS(tstatus) || !thread_info.TebBaseAddress ||
        static_cast<DWORD>(reinterpret_cast<ULONG_PTR>(
            thread_info.ClientId.UniqueThread)) != GetCurrentThreadId())
        return 14;

    // Independently query an exact synthetic virtual allocation through the
    // native NT API. VirtualAlloc/VirtualFree create no persistent state.
    void* memory = VirtualAlloc(nullptr, 4096, MEM_RESERVE | MEM_COMMIT,
                                PAGE_READWRITE);
    if (!memory) return 15;
    MEMORY_BASIC_INFORMATION memory_info = {};
    SIZE_T memory_bytes = 0;
    const NTSTATUS mstatus = NtQueryVirtualMemory(
        GetCurrentProcess(), memory, MemoryBasicInformation,
        &memory_info, sizeof(memory_info), &memory_bytes);
    const bool memory_ok = NT_SUCCESS(mstatus) &&
        memory_info.BaseAddress == memory &&
        memory_info.RegionSize >= 4096 &&
        memory_info.State == MEM_COMMIT;
    if (!VirtualFree(memory, 0, MEM_RELEASE)) return 16;
    if (!memory_ok) return 17;

    // Only a fixed category exits to public CI; pointers stay process-local.
    std::puts("PASS: native_nt_process_thread_event_and_virtual_memory");
    return 0;
}
