#ifndef UI4ME_H
#define UI4ME_H
#include <stdint.h>

#if defined(_WIN32)
# define UI4ME_CALL __cdecl
#else
# define UI4ME_CALL
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ABI 1. All strings are UTF-8, NUL terminated, borrowed and read-only.
 * Copy command output before the next command on this thread. Never free it.
 * The caller owns callback and user until destroy succeeds.
 * Return values: 0 success, 1 invalid argument, 2 lifecycle, 3 wrong thread,
 * 4 stale handle, 5 resource limit, 6 native runtime, 7 callback, 8 poisoned,
 * 9 IO. The diagnostic is in ui4me_last_error(), on the calling thread.
 * Commands/create/run/destroy are owner-thread only. post/stop are thread-safe.
 * A callback must never unwind or throw through this boundary. */
typedef int32_t (UI4ME_CALL *ui4me_callback)(uint64_t session,
                                          const char *event_json,
                                          void *user);
uint32_t UI4ME_CALL ui4me_abi_version(void);
const char *UI4ME_CALL ui4me_build_info(void);
const char *UI4ME_CALL ui4me_last_error(void);
int32_t UI4ME_CALL ui4me_session_create(const char *config_json,
                                      ui4me_callback callback,
                                      void *user,
                                      uint64_t *out_session);
int32_t UI4ME_CALL ui4me_session_command(uint64_t session,
                                       const char *command_json,
                                       const char **out_json);
int32_t UI4ME_CALL ui4me_session_run(uint64_t session);
int32_t UI4ME_CALL ui4me_session_post(uint64_t session, uint64_t token);
int32_t UI4ME_CALL ui4me_session_stop(uint64_t session);
int32_t UI4ME_CALL ui4me_session_destroy(uint64_t session);

#ifdef __cplusplus
}
#endif
#endif
