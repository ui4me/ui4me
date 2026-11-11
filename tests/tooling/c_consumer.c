#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ui4me.h"
#ifdef _WIN32
#include <windows.h>
#define LOAD(p) LoadLibraryW(p)
#define SYMBOL(h,n) GetProcAddress(h,n)
#else
#include <dlfcn.h>
#define LOAD(p) dlopen(p, RTLD_NOW | RTLD_LOCAL)
#define SYMBOL(h,n) dlsym(h,n)
#endif

typedef uint32_t (UI4ME_CALL *abi_fn)(void);
typedef int32_t (UI4ME_CALL *create_fn)(const char *, ui4me_callback, void *, uint64_t *);
typedef int32_t (UI4ME_CALL *id_fn)(uint64_t);
typedef int32_t (UI4ME_CALL *command_fn)(uint64_t, const char *, const char **);
typedef int32_t (UI4ME_CALL *complete_fn)(uint64_t, uint64_t);
static id_fn stop_session;
static int32_t UI4ME_CALL on_event(uint64_t id, const char *json, void *context) {
    if (strstr(json, "\"completion\"")) {
        ++*(int *)context;
        return stop_session(id) == 0 ? 0 : -1;
    }
    return 0;
}
#ifdef _WIN32
int wmain(int argc, wchar_t **argv) {
#else
int main(int argc, char **argv) {
#endif
    if (argc != 2) return 2;
    void *handle = (void *)LOAD(argv[1]);
    if (!handle) return 3;
    abi_fn abi;
    create_fn create;
    command_fn command;
    complete_fn complete;
    id_fn run_session, destroy;
    /* memcpy avoids ISO C object/function pointer cast diagnostics on POSIX. */
    void *symbol = (void *)SYMBOL(handle, "ui4me_abi_version"); memcpy(&abi, &symbol, sizeof abi);
    symbol = (void *)SYMBOL(handle, "ui4me_session_create"); memcpy(&create, &symbol, sizeof create);
    symbol = (void *)SYMBOL(handle, "ui4me_session_command"); memcpy(&command, &symbol, sizeof command);
    symbol = (void *)SYMBOL(handle, "ui4me_session_complete"); memcpy(&complete, &symbol, sizeof complete);
    symbol = (void *)SYMBOL(handle, "ui4me_session_run"); memcpy(&run_session, &symbol, sizeof run_session);
    symbol = (void *)SYMBOL(handle, "ui4me_session_stop"); memcpy(&stop_session, &symbol, sizeof stop_session);
    symbol = (void *)SYMBOL(handle, "ui4me_session_destroy"); memcpy(&destroy, &symbol, sizeof destroy);
    if (!abi || !create || !command || !complete || !run_session || !stop_session || !destroy || abi() != 1) return 4;
    uint64_t previous = 0;
    for (int i = 0; i < 2; ++i) {
        uint64_t id = 0;
        int completions = 0;
        const char *reply = NULL;
        if (create("{\"backend\":\"headless\"}", on_event, &completions, &id) != 0 || !id || id == previous) return 5;
        if (command(id, "{\"op\":\"reserve_completion\",\"token\":17}", &reply) != 0 || !reply) return 8;
        if (complete(id, 17) != 0 || complete(id, 17) != 4) return 9;
        if (run_session(id) != 0 || completions != 1 || destroy(id) != 0) return 6;
        if (stop_session(id) == 0) return 7;
        previous = id;
    }
    puts("C ABI consumer passed");
    return 0;
}
