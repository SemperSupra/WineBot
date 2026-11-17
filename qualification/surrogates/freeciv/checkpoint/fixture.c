/* Public-safe source-known x86_64/Linux breakpoint checkpoint fixture.
 * The debugger is its direct parent. No network, game data, or private assets.
 */
#define _GNU_SOURCE
#include <signal.h>
#include <sys/ptrace.h>
#include <unistd.h>

volatile unsigned long long controlled_state = 42ULL;

__attribute__((noinline)) void apply_action(void) {
    controlled_state += 1;
    __asm__ __volatile__("" ::: "memory");
}

__attribute__((noinline)) void observe_after(void) {
    __asm__ __volatile__("" ::: "memory");
}

int main(void) {
    if (ptrace(PTRACE_TRACEME, 0, 0, 0) == -1) return 70;
    raise(SIGSTOP);
    apply_action();
    observe_after();
    return controlled_state == 43ULL ? 0 : 71;
}
