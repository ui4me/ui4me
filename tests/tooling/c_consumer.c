#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ui4me.h"
#ifdef _WIN32
#include <windows.h>
#define LOAD(p) LoadLibraryA(p)
#define SYMBOL(h,n) GetProcAddress(h,n)
#else
#include <dlfcn.h>
#define LOAD(p) dlopen(p, RTLD_NOW | RTLD_LOCAL)
#define SYMBOL(h,n) dlsym(h,n)
#endif

typedef uint32_t (*abi_fn)(void);
typedef int32_t (*create_fn)(const char *, ui4me_callback, void *, uint64_t *);
typedef int32_t (*id_fn)(uint64_t);
static id_fn stop_session;
static int32_t on_event(uint64_t id, const char *json, void *context) {
    (void)context;
    if (strstr(json, "started")) return stop_session(id) == 0 ? 0 : -1;
    return 0;
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    void *handle = (void *)LOAD(argv[1]);
    if (!handle) return 3;
    abi_fn abi;
    create_fn create;
    id_fn run_session, destroy;
    /* memcpy avoids ISO C object/function pointer cast diagnostics on POSIX. */
    void *symbol = (void *)SYMBOL(handle, "ui4me_abi_version"); memcpy(&abi, &symbol, sizeof abi);
    symbol = (void *)SYMBOL(handle, "ui4me_session_create"); memcpy(&create, &symbol, sizeof create);
    symbol = (void *)SYMBOL(handle, "ui4me_session_run"); memcpy(&run_session, &symbol, sizeof run_session);
    symbol = (void *)SYMBOL(handle, "ui4me_session_stop"); memcpy(&stop_session, &symbol, sizeof stop_session);
    symbol = (void *)SYMBOL(handle, "ui4me_session_destroy"); memcpy(&destroy, &symbol, sizeof destroy);
    if (!abi || !create || !run_session || !stop_session || !destroy || abi() != 1) return 4;
    uint64_t previous = 0;
    for (int i = 0; i < 2; ++i) {
        uint64_t id = 0;
        if (create("{\"backend\":\"headless\"}", on_event, NULL, &id) != 0 || !id || id == previous) return 5;
        if (run_session(id) != 0 || destroy(id) != 0) return 6;
        if (stop_session(id) == 0) return 7;
        previous = id;
    }
    puts("C ABI consumer passed");
    return 0;
}
