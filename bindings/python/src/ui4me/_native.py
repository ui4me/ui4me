"""The only ctypes boundary. All native borrowed strings are copied immediately."""
from __future__ import annotations

import ctypes as C
import json
import os
from pathlib import Path
import platform
import threading


class Ui4meError(RuntimeError):
    def __init__(self, message: str, code: int = -1):
        super().__init__(message)
        self.code = code


CALLBACK = C.CFUNCTYPE(C.c_int32, C.c_uint64, C.c_char_p, C.c_void_p)
_instance = None
_load_lock = threading.Lock()


def native_path() -> Path:
    override = os.environ.get("UI4ME_NATIVE_LIB")
    if override:
        path = Path(override)
        if not path.is_absolute():
            raise Ui4meError("UI4ME_NATIVE_LIB must be an absolute file path")
    else:
        if platform.machine().lower() not in ("x86_64", "amd64"):
            raise Ui4meError("This package supports x64 Windows and Linux only")
        names = {"Windows": "ui4me_core.dll", "Linux": "libui4me_core.so"}
        name = names.get(platform.system())
        if name is None:
            raise Ui4meError("This package supports Windows and Linux only")
        path = Path(__file__).resolve().parent / "_native" / name
    if not path.is_file():
        raise Ui4meError(f"Native runtime not found: {path}. Install a platform wheel or build the repository.")
    return path.resolve()


class Library:
    def __init__(self):
        self.path = native_path()
        try:
            self.dll = C.CDLL(str(self.path))
        except OSError as error:
            raise Ui4meError(f"Cannot load {self.path}: {error}") from error
        signatures = {
            "abi_version": ([], C.c_uint32),
            "build_info": ([], C.c_char_p),
            "last_error": ([], C.c_char_p),
            "session_create": ([C.c_char_p, CALLBACK, C.c_void_p, C.POINTER(C.c_uint64)], C.c_int32),
            "session_command": ([C.c_uint64, C.c_char_p, C.POINTER(C.c_void_p)], C.c_int32),
            "session_run": ([C.c_uint64], C.c_int32),
            "session_post": ([C.c_uint64, C.c_uint64], C.c_int32),
            "session_stop": ([C.c_uint64], C.c_int32),
            "session_destroy": ([C.c_uint64], C.c_int32),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.dll, "ui4me_" + name)
            function.argtypes = args
            function.restype = result
            setattr(self, name, function)
        if self.abi_version() != 1:
            raise Ui4meError("Unsupported ui4me ABI; this binding requires ABI 1")

    def check(self, status: int) -> None:
        if status:
            message = self.last_error()
            raise Ui4meError(message.decode("utf-8", "replace") if message else "Native operation failed", status)

    def command(self, session: int, command: dict) -> dict:
        payload = json.dumps(command, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError("Command exceeds 2 MiB")
        out = C.c_void_p()
        self.check(self.session_command(session, payload, C.byref(out)))
        data = C.string_at(out.value) if out.value else b"{}"
        return json.loads(data)


def library() -> Library:
    global _instance
    with _load_lock:
        if _instance is None:
            _instance = Library()
        return _instance


def build_info() -> dict:
    native = library()
    value = json.loads(native.build_info())
    return {**value, "abi": int(native.abi_version()), "library_path": str(native.path)}
