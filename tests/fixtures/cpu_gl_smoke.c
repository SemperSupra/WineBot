/* Public synthetic Wine/WGL workload. All inputs and output are allowlisted.
 * Does not include any game assets, private scenes, or system identity.
 */
#include <windows.h>
#include <GL/gl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int bounded(const char *s, int min, int max, int fallback) {
    if (!s) return fallback;
    char *end = NULL;
    long n = strtol(s, &end, 10);
    return end != s && *end == '\0' && n >= min && n <= max ? (int)n : -1;
}

int main(int argc, char **argv) {
    int frames = bounded(argc > 1 ? argv[1] : NULL, 1, 120, 1);
    int triangles = bounded(argc > 2 ? argv[2] : NULL, 1, 2048, 1);
    int width = bounded(argc > 3 ? argv[3] : NULL, 160, 1280, 320);
    int fill = bounded(argc > 4 ? argv[4] : NULL, 0, 1, 0);
    if (frames < 0 || triangles < 0 || width < 0 || fill < 0) return 20;
    if (fill && frames * triangles > 256) return 22;
    int height = width * 3 / 4;

    HINSTANCE instance = GetModuleHandleA(NULL);
    WNDCLASSA cls = {0};
    cls.lpfnWndProc = DefWindowProcA;
    cls.hInstance = instance;
    cls.lpszClassName = "WineBotCpuGlFixture";
    if (!RegisterClassA(&cls)) return 10;
    HWND window = CreateWindowA(cls.lpszClassName, "Synthetic GL fixture",
                                WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                CW_USEDEFAULT, CW_USEDEFAULT, width, height,
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

    /* Win32 CreateWindow dimensions include nonclient borders. The
     * framebuffer is only the client rectangle, including on Wine/X11.
     */
    RECT client = {0};
    if (!GetClientRect(window, &client)) return 25;
    int client_width = client.right - client.left;
    int client_height = client.bottom - client.top;
    if (client_width < 4 || client_height < 4) return 25;
    glViewport(0, 0, client_width, client_height);
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glOrtho(-1.0, 1.0, -1.0, 1.0, -1.0, 1.0);
    LARGE_INTEGER frequency, start, stop;
    if (!QueryPerformanceFrequency(&frequency) || !frequency.QuadPart) return 21;
    if (!QueryPerformanceCounter(&start)) return 21;
    for (int f = 0; f < frames; ++f) {
        glClearColor(0.1f, 0.2f, 0.3f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);
        glBegin(GL_TRIANGLES);
        for (int t = 0; t < triangles; ++t) {
            float x = (float)((t % 31) - 15) / 16.0f;
            float y = (float)(((t / 31) % 23) - 11) / 12.0f;
            glColor3f(0.7f, 0.3f, 0.5f);
            if (fill) {
                float offset = (float)(t % 5) * 0.01f;
                glVertex2f(-1.0f + offset, -1.0f);
                glVertex2f(1.0f, -1.0f + offset);
                glVertex2f(-1.0f, 1.0f);
            } else {
                glVertex2f(x, y);
                glVertex2f(x + 0.015f, y);
                glVertex2f(x, y + 0.015f);
            }
        }
        glEnd();
        glFinish();
        /* Sample an intentionally untouched upper-right pixel in the back
         * buffer. A successful swap alone does not prove raster output.
         * Clear RGB 0.1, 0.2, 0.3 should quantize near 26, 51, 77.
         */
        GLubyte pixel[3] = {0, 0, 0};
        glReadBuffer(GL_BACK);
        glReadPixels(client_width - 2, client_height - 2, 1, 1, GL_RGB,
                     GL_UNSIGNED_BYTE, pixel);
        if (glGetError() != GL_NO_ERROR) return 17;
        if (pixel[0] < 20 || pixel[0] > 33 ||
            pixel[1] < 45 || pixel[1] > 58 ||
            pixel[2] < 70 || pixel[2] > 84) return 24;
        if (!SwapBuffers(dc)) return 16;
    }
    if (!QueryPerformanceCounter(&stop)) return 21;
    unsigned long elapsed_us = (unsigned long)(1000000.0 *
        (double)(stop.QuadPart - start.QuadPart) / (double)frequency.QuadPart);
    printf("WINE_OPENGL_LLVMPIPE_OK frames=%d triangles=%d width=%d fill=%d elapsed_us=%lu\n",
           frames, triangles, width, fill, elapsed_us);
    wglMakeCurrent(NULL, NULL);
    wglDeleteContext(context);
    ReleaseDC(window, dc);
    DestroyWindow(window);
    return 0;
}
