# Implementation coordination contract

This internal contract is folded into docs before delivery. Version 0.1.0, ABI 1; Rust crate name ui4me-core, output ui4me_core.dll / libui4me_core.so. Package paths preserve these names. Supported targets: win-x64 and linux-x64. Source status: reconstructed, not executed.

## C interface

uint32_t ui4me_abi_version(void);
const char *ui4me_build_info(void); // borrowed UTF-8 JSON
const char *ui4me_last_error(void); // thread-local borrowed UTF-8 string
typedef int32_t (*ui4me_callback)(uint64_t session, const char *event_json, void *user);
int32_t ui4me_session_create(const char *config_json, ui4me_callback cb, void *user, uint64_t *out);
int32_t ui4me_session_command(uint64_t session, const char *command_json, const char **out_json);
int32_t ui4me_session_run(uint64_t session);
int32_t ui4me_session_post(uint64_t session, uint64_t token);
int32_t ui4me_session_stop(uint64_t session);
int32_t ui4me_session_destroy(uint64_t session);

Return 0 success, nonzero error. Callback returns 0 continue, 1 veto only close_requested, negative callback failure. Never throw across C. Every borrowed string must be copied immediately; output JSON valid until next command on that same thread. Exactly one active session, create/run/command/destroy owner thread; post/stop any thread. IDs are monotonic and stale IDs rejected. Native app must run on process main thread; PowerShell uses a dedicated owner thread only on Windows/Linux where the core explicitly enables it. Config: {"backend":"native"|"headless","app_id":"org.ui4me.demo"}. Native repeated sessions in one process must reuse a thread-local event loop or explicitly return restart_required; prefer reusable loop.

## Commands and events

Commands: {"op":"open","title":"...","html":"...","width":640,"height":480} -> {"window":id}; {"op":"set_text","window":id,"element":"id","text":"..."}; {"op":"get_value","window":id,"element":"id"} -> {"value":"..."}; {"op":"close","window":id}; {"op":"set_title","window":id,"title":"..."}; {"op":"resize","window":id,"width":... ,"height":...}; {"op":"snapshot","window":id,"path":"..."}; {"op":"timer","token":id,"milliseconds":n,"repeat":bool}; {"op":"cancel_timer","token":id}; {"op":"stats"} -> counts.

Events JSON: {"type":"started"}; {"type":"post","token":n}; {"type":"timer","token":n}; {"type":"click"|"change"|"close_requested"|"closed"|"resized","window":n,"element":"id" optional,"value":"..." optional}; {"type":"stopped"}. Callback calls may issue commands; never hold core mutex while calling foreign code. Start event occurs when the loop can accept open. Native open before run queues a window request. Headless backend supports lifecycle and deterministic snapshot; it is never native evidence.

## Paths / developer interface

Python: bindings/python/pyproject.toml; bindings/python/src/ui4me; bindings/python/tests. Native package path ui4me/_native/<filename>. ctypes wrapper public App, Window, exceptions; App(backend='native'), app.open(html,title='ui4me',width=640,height=480), app.run(), app.stop(), app.post(callable), app.timer(milliseconds,callable,repeat=False), context-manager cleanup. Window.on(event,handler), set_text(element,text), get_value(element), close(), set_title(title), resize(width,height), snapshot(path). Handler signature handler(event_dict), closures encouraged. Examples must agree. Python tests use unittest and explicit UI4ME_NATIVE_LIB developer override. python -m ui4me doctor|demo.

PowerShell: bindings/powershell/Ui4me/Ui4me.psd1 + psm1; bindings/powershell/Ui4me.Managed/Ui4me.Managed.csproj (net8.0; PowerShell 7.4 reference floor; SDK10); native path Ui4me/runtimes/<rid>/native/<filename>; managed path Ui4me/lib/Ui4me.Managed.dll. Public 7 cmdlets Invoke-Ui4meApp, Get-Ui4meInfo, New-Ui4meWindow, Register-Ui4meEvent, Set-Ui4meText, Get-Ui4meValue, Stop-Ui4meApp. Examples and smoke script include headless path. Managed bridge must use UTF8, scoped native resolver, callback roots, owner confinement, clean disposal, bounded posts/work and exception propagation. Root tool packages managed build output into lib/.

dev.py operations: doctor, lock, build, test, package, assemble, report, qualify, publish, verify, source-zip. Common flags --binding core|python|powershell|all|tools --profile dev|release; tests --suite unit|installed|native|all --manifest PATH --interactive; default host auto. Package manifest uses source_id, git_revision, version, platform, artifacts[{kind,path,sha256,size}]. Native scenarios require real display and manual attestation + screenshot; never qualify automated headless substitute. Publishing takes qualified final manifest; default dry-run. Initial archive is source-only and unqualified.

## Scenario catalog shared IDs

F01 clean_install; F02 native_startup; F03 input_state_change; F04 window_lifetime_resize_multiple; F05 close_veto_forced_stop; F06 owner_thread_dispatch; F07 cancellation_stop_races; F08 same_process_native_reuse; F09 abi_callback_lifetime; F10 bounds_idle; F11 resources_diagnostics; F12 release_upgrade. F01/F09/F11/F12 may use installed headless. Native F02-F08 and F10 require native interactive evidence for release. This preserves the IDs in the original foundation research.
