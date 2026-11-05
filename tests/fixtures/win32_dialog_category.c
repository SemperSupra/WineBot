/* Synthetic public RDTE: classify a BZFlag Win32 startup dialog.
 * Emits allowlisted category ONLY, never window text or host identity.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <ctype.h>
#include <stdio.h>
#include <string.h>

enum ErrorBits {
    E_GRAPHICS = 1, E_ASSETS = 2, E_AUDIO = 4, E_NETWORK = 8,
    E_GENERIC = 16
};
static int flags = 0;
static int windows_seen = 0;
static int children_seen = 0;

static int contains(const char *haystack, const char *needle) {
    size_t n = strlen(needle);
    if (!n) return 0;
    for (const char *p = haystack; *p; ++p) {
        size_t i = 0;
        while (i < n && p[i] &&
               tolower((unsigned char)p[i]) ==
               tolower((unsigned char)needle[i])) ++i;
        if (i == n) return 1;
    }
    return 0;
}

static void classify(const char *s) {
    if (contains(s, "opengl") || contains(s, "graphics") ||
        contains(s, "glx") || contains(s, "video") ||
        contains(s, "display") || contains(s, "pixel format"))
        flags |= E_GRAPHICS;
    if (contains(s, "data") || contains(s, "resource") ||
        contains(s, "texture") || contains(s, "file") ||
        contains(s, "font") || contains(s, "directory"))
        flags |= E_ASSETS;
    if (contains(s, "audio") || contains(s, "sound") ||
        contains(s, "openal"))
        flags |= E_AUDIO;
    if (contains(s, "network") || contains(s, "server") ||
        contains(s, "connection") || contains(s, "dns"))
        flags |= E_NETWORK;
    if (contains(s, "error") || contains(s, "failed") ||
        contains(s, "unable") || contains(s, "fatal"))
        flags |= E_GENERIC;
}

static BOOL CALLBACK child(HWND h, LPARAM unused) {
    (void)unused;
    char value[512] = {0};
    DWORD_PTR copied = 0;
    children_seen++;
    if (SendMessageTimeoutA(h, WM_GETTEXT, sizeof(value),
                            (LPARAM)value, SMTO_ABORTIFHUNG | SMTO_BLOCK,
                            150, &copied) && copied)
        classify(value);
    return TRUE;
}

static BOOL CALLBACK top(HWND h, LPARAM unused) {
    (void)unused;
    char title[256] = {0};
    if (!IsWindowVisible(h)) return TRUE;
    GetWindowTextA(h, title, sizeof(title));
    if (!contains(title, "bzflag")) return TRUE;
    windows_seen++;
    classify(title);
    EnumChildWindows(h, child, 0);
    return TRUE;
}

int main(void) {
    EnumWindows(top, 0);
    const char *category = "unknown";
    if (flags & E_GRAPHICS) category = "graphics";
    else if (flags & E_ASSETS) category = "resources";
    else if (flags & E_AUDIO) category = "audio";
    else if (flags & E_NETWORK) category = "network";
    else if (flags & E_GENERIC) category = "generic_error";
    else if (!windows_seen) category = "no_window";
    printf("WIN32_DIALOG_CATEGORY=%s\n", category);
    printf("WIN32_DIALOG_CHILDREN_PRESENT=%d\n", children_seen > 0);
    return 0;
}
