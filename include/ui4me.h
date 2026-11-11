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
 * Destroy is rejected while run or ANY callback is active, including stopped.
 * A stopped phase does not imply that run has returned.
 * Return values: 0 success, 1 invalid argument, 2 lifecycle, 3 wrong thread,
 * 4 stale handle, 5 resource limit, 6 native runtime, 7 callback, 8 poisoned,
 * 9 IO. The diagnostic is in ui4me_last_error(), on the calling thread.
 * Commands/create/run/destroy are owner-thread only. post/stop/complete are thread-safe.
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
/* Added in package 0.2, ABI 1. Before starting a worker, reserve on the owner:
 *   {"op":"reserve_completion","token":N}
 * complete publishes N using its reserved slot independently of ordinary posts.
 * The owner receives {"type":"completion","token":N} at most once.
 * Cancel on the owner with {"op":"cancel_completion","token":N}.
 * Up to 128 tickets may be reserved; stop retires outstanding tickets.
 * The binding owns payload/result storage and must settle it on stop/disposal. */
int32_t UI4ME_CALL ui4me_session_complete(uint64_t session, uint64_t token);
int32_t UI4ME_CALL ui4me_session_destroy(uint64_t session);

#ifdef __cplusplus
}
#endif
#endif
