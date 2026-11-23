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

    // Only a fixed category exits to public CI; pointers stay process-local.
    std::puts("PASS: native_nt_process_peb_and_event_handle");
    return 0;
}
