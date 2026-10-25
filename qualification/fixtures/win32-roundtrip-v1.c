/*
 * Synthetic WineBot/WinBot cross-runtime file roundtrip.
 *
 * License: MIT. No network, registry, shell or GUI behavior.
 * Compile the same PE binary once and run precisely those bytes in both lanes.
 * Run only from a fresh, writable, disposable working directory.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define FIXTURE_NAME L"winebot-compat-roundtrip-v1.dat"
#define EXPECTED_LINE "WB_COMPAT_ROUNDTRIP_V1:PASS\n"

static const unsigned char FIXTURE_BYTES[] = "WB-FIXTURE-V1\nAa0_\n";

int main(void) {
    HANDLE handle = INVALID_HANDLE_VALUE;
    unsigned char observed[sizeof(FIXTURE_BYTES)];
    DWORD wrote = 0;
    DWORD received = 0;
    DWORD remaining = 0;
    BOOL good = FALSE;

    handle = CreateFileW(FIXTURE_NAME, GENERIC_WRITE, 0, NULL,
                         CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (handle == INVALID_HANDLE_VALUE) {
        return 41;
    }
    good = WriteFile(handle, FIXTURE_BYTES, (DWORD)(sizeof(FIXTURE_BYTES) - 1),
                     &wrote, NULL);
    if (!CloseHandle(handle) || !good || wrote != sizeof(FIXTURE_BYTES) - 1) {
        return 42;
    }

    handle = CreateFileW(FIXTURE_NAME, GENERIC_READ, FILE_SHARE_READ, NULL,
                         OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (handle == INVALID_HANDLE_VALUE) {
        return 43;
    }
    memset(observed, 0, sizeof(observed));
    good = ReadFile(handle, observed, (DWORD)sizeof(observed), &received, NULL);
    if (!CloseHandle(handle) || !good || received != sizeof(FIXTURE_BYTES) - 1 ||
        memcmp(observed, FIXTURE_BYTES, sizeof(FIXTURE_BYTES) - 1) != 0) {
        return 44;
    }
    if (!DeleteFileW(FIXTURE_NAME)) {
        return 45;
    }
    remaining = (DWORD)strlen(EXPECTED_LINE);
    return fwrite(EXPECTED_LINE, 1, remaining, stdout) == remaining ? 0 : 46;
}
