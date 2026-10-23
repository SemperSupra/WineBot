/* Synthetic public fixture: validate Win32 WGL -> Wine -> Mesa LLVMpipe.
 * No private application, saved game, proprietary media, or host identity.
 */
#include <windows.h>
#include <GL/gl.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    HINSTANCE instance = GetModuleHandleA(NULL);
    WNDCLASSA cls = {0};
    cls.lpfnWndProc = DefWindowProcA;
    cls.hInstance = instance;
    cls.lpszClassName = "WineBotCpuGlFixture";
    if (!RegisterClassA(&cls)) return 10;

    HWND window = CreateWindowA(cls.lpszClassName, "Synthetic GL fixture",
                                WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                CW_USEDEFAULT, CW_USEDEFAULT, 320, 240,
                                NULL, NULL, instance, NULL);
    if (!window) return 11;

    HDC dc = GetDC(window);
    if (!dc) return 12;
    PIXELFORMATDESCRIPTOR pfd = {0};
    pfd.nSize = sizeof(pfd);
    pfd.nVersion = 1;
    pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    pfd.iPixelType = PFD_TYPE_RGBA;
    pfd.cColorBits = 24;
    pfd.cDepthBits = 16;
    int format = ChoosePixelFormat(dc, &pfd);
    if (!format || !SetPixelFormat(dc, format, &pfd)) return 13;

    HGLRC context = wglCreateContext(dc);
    if (!context || !wglMakeCurrent(dc, context)) return 14;
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    if (!renderer || !strstr(renderer, "llvmpipe")) return 15;

    glViewport(0, 0, 320, 240);
    glClearColor(0.1f, 0.2f, 0.3f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    glFinish();
    if (!SwapBuffers(dc)) return 16;

    puts("WINE_OPENGL_LLVMPIPE_OK");
    wglMakeCurrent(NULL, NULL);
    wglDeleteContext(context);
    ReleaseDC(window, dc);
    DestroyWindow(window);
    return 0;
}
