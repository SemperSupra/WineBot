/* SPDX-License-Identifier: MIT
 * Synthetic PE64: real Win32 module, heap and region queries under Wine.
 * Output is ephemeral and MUST NOT be published in public job logs.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <stdint.h>
#include <stdio.h>
static void record(const char *kind, DWORD pid, const void *address, SIZE_T size) {
    printf("{\"schema\":\"wine-introspection-rdte/v0\","
           "\"source\":\"WIN32_API_ENUMERATED\",\"kind\":\"%s\","
           "\"process_id\":%lu,\"address_space\":\"windows_process_va\","
           "\"address\":\"0x%llx\",\"size_bytes\":%llu,"
           "\"object_id\":null,\"generation\":null,\"semantic_type\":null,"
           "\"snapshot\":\"best_effort\",\"coverage\":\"partial\"}\n",
           kind,(unsigned long)pid,(unsigned long long)(uintptr_t)address,
           (unsigned long long)size);
}
int main(void) {
    HANDLE heap=GetProcessHeap();
    HMODULE module=GetModuleHandleW(NULL);
    DWORD pid=GetCurrentProcessId();
    MODULEINFO image={0};
    PROCESS_HEAP_ENTRY entry={0};
    MEMORY_BASIC_INFORMATION region={0};
    void *p=NULL;
    SIZE_T live_size=0;
    unsigned int scanned=0;
    if (!heap || !module || !pid) return 2;
    if (!GetModuleInformation(GetCurrentProcess(),module,&image,sizeof(image)) ||
        !image.lpBaseOfDll || image.SizeOfImage<4096) return 3;
    p=HeapAlloc(heap,HEAP_ZERO_MEMORY,256);
    if (!p) return 4;
    if (!HeapLock(heap)) return 5;
    while (scanned++ < 100000 && HeapWalk(heap,&entry)) {
        if ((entry.wFlags & PROCESS_HEAP_ENTRY_BUSY) && entry.lpData==p) {
            live_size=entry.cbData;
            break;
        }
    }
    if (!HeapUnlock(heap)) return 6;
    if (live_size<256) return 7;
    if (VirtualQuery(p,&region,sizeof(region))!=sizeof(region) ||
        region.State!=MEM_COMMIT || !region.BaseAddress ||
        region.RegionSize<256) return 8;
    record("module",pid,image.lpBaseOfDll,(SIZE_T)image.SizeOfImage);
    record("heap_allocation",pid,p,live_size);
    record("memory_region",pid,region.BaseAddress,region.RegionSize);
    if (fflush(stdout)!=0) return 9;
    if (!HeapFree(heap,0,p)) return 10;
    return 0;
}
