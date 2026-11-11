#!/usr/bin/env python3
"""Real-input keyboard-layout and IME journey on a private virtual KWin (Core 0.5 F0501/F0502).

    python3 input_journey.py --out DIR -- <probe command ...>

The probe command is ``tests/native/input_probe.py`` (Python) or ``input_probe.ps1``
(PowerShell) and must take ``{state}`` and ``{commands}`` placeholders. A private D-Bus session
and ``kwin_wayland --virtual`` run with a private ``kxkbrc`` (layouts us, cz, us(intl), de) and
``--inputmethod`` pointing at the scripted input method ``scriptime.c``. Keys go through KWin's
fake_input as evdev keycodes, so the compositor's XKB keymap (dead keys, AltGr, Compose, repeat)
and the text-input-v3 path produce the characters. Result: DIR/journey.json. Automated
compositor input on a virtual output, not a person; label evidence accordingly.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from chat_journey import (Input, build_fakeinput, isolated_environment, read_state,  # noqa: E402
                          reap_private_bus, use_virtual_display, wait, window_geometry)

# evdev keycodes
K = {"1": 2, "2": 3, "5": 6, "6": 7, "8": 9, "minus": 12, "equal": 13, "bs": 14, "tab": 15,
     "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23, "o": 24, "p": 25,
     "lbracket": 26, "enter": 28, "lctrl": 29, "a": 30, "s": 31, "d": 32, "semicolon": 39,
     "apostrophe": 40, "grave": 41, "lshift": 42, "z": 44, "x": 45, "c": 46, "v": 47, "b": 48,
     "n": 49, "lalt": 56, "space": 57, "ralt": 100, "home": 102, "end": 107}
LAYOUTS = ["us", "cz", "us(intl)", "de"]
KXKBRC = """[Layout]
DisplayNames=,,,
LayoutList=us,cz,us,de
Model=pc105
Use=true
VariantList=,,intl,
ResetOldOptions=true
Options=
"""


def build_scriptime(out: Path) -> Path:
    binary = out / "scriptime"
    xml = HERE / "input-method-unstable-v1.xml"
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(["wayland-scanner", "client-header", xml, f"{t}/input-method-client-protocol.h"], check=True)
        subprocess.run(["wayland-scanner", "private-code", xml, f"{t}/input-method-protocol.c"], check=True)
        subprocess.run(["gcc", "-O1", f"-I{t}", "-o", binary, HERE / "scriptime.c", f"{t}/input-method-protocol.c",
                        "-lwayland-client"], check=True)
    return binary


class Ime:
    """Talks to scriptime over its FIFOs."""

    def __init__(self, cmd: Path, reply: Path):
        self.cmd = cmd
        self.reply = reply
        self.r = None

    def __call__(self, line: str, timeout: float = 5.0) -> str:
        if self.r is None:
            self.r = os.open(self.reply, os.O_RDONLY | os.O_NONBLOCK)
        with open(self.cmd, "w", encoding="utf-8") as w:
            w.write(line + "\n")
        deadline = time.monotonic() + timeout
        buf = b""
        while time.monotonic() < deadline:
            try:
                chunk = os.read(self.r, 65536)
            except BlockingIOError:
                chunk = b""
            buf += chunk
            if buf.endswith(b"\n"):
                return buf.decode("utf-8").strip()
            time.sleep(0.02)
        raise TimeoutError(f"scriptime did not answer {line!r}")


def journey(out: Path, command: list[str]) -> dict:
    cases: list[dict] = []
    state_path = out / "state.json"
    commands = out / "commands.jsonl"
    commands.write_text("", encoding="utf-8")
    command = [c.replace("{state}", str(state_path)).replace("{commands}", str(commands)) for c in command]
    runtime = Path(os.environ["XDG_RUNTIME_DIR"])
    sock = f"ui4me-input-{os.getpid()}"
    log = runtime / f"{sock}.log"
    config = Path(tempfile.mkdtemp(prefix="ui4me-kwin-config-"))
    (config / "kxkbrc").write_text(KXKBRC, encoding="utf-8")
    ime_cmd, ime_reply = out / "ime.cmd", out / "ime.reply"
    for fifo in (ime_cmd, ime_reply):
        if fifo.exists():
            fifo.unlink()
        os.mkfifo(fifo)
    scriptime = build_scriptime(out)
    env = dict(os.environ, KWIN_WAYLAND_NO_PERMISSION_CHECKS="1", XDG_CONFIG_HOME=str(config),
               UI4ME_IME_CMD=str(ime_cmd), UI4ME_IME_REPLY=str(ime_reply))
    env.pop("DISPLAY", None)
    kwin = subprocess.Popen(["kwin_wayland", "--virtual", "--no-lockscreen", "--socket", sock, "--width", "1280",
                             "--height", "900", "--inputmethod", str(scriptime)],
                            env=env, stdout=log.open("w"), stderr=subprocess.STDOUT)
    app = None
    fake = None
    app_env = dict(env)
    app_env.pop("XDG_CONFIG_HOME")
    try:
        for _ in range(100):
            if (runtime / sock).exists():
                break
            time.sleep(0.1)
        time.sleep(1.0)
        app_env["WAYLAND_DISPLAY"] = sock
        os.environ["WAYLAND_DISPLAY"] = sock
        use_virtual_display(sock)
        app_log = (out / "app.log").open("w")
        app = subprocess.Popen(command, env=app_env, stdout=app_log, stderr=subprocess.STDOUT)
        fake = Input(build_fakeinput(out))
        ime = Ime(ime_cmd, ime_reply)
        geo: dict = {}
        sent = {"n": 0}

        def host(ack: bool = True, **op) -> None:
            with commands.open("a", encoding="utf-8") as f:
                f.write(json.dumps(op, ensure_ascii=False) + "\n")
            sent["n"] = commands.stat().st_size
            if ack:
                wait(state_path, lambda s: s["commands"] >= sent["n"])

        def case(name, action):
            started = time.monotonic()
            try:
                detail = action()
                cases.append({"id": name, "status": "passed", "details": detail, "seconds": round(time.monotonic() - started, 2)})
            except Exception as error:  # record and continue: later cases report independently
                cases.append({"id": name, "status": "failed", "details": f"{type(error).__name__}: {error}"})

        def layout(index: int) -> None:
            subprocess.run(["qdbus6", "org.kde.keyboard", "/Layouts", "org.kde.KeyboardLayouts.setLayout", str(index)],
                           check=True, capture_output=True)
            for _ in range(50):
                got = subprocess.run(["qdbus6", "org.kde.keyboard", "/Layouts", "org.kde.KeyboardLayouts.getLayout"],
                                     capture_output=True, text=True).stdout.strip()
                if got == str(index):
                    return
                time.sleep(0.1)
            raise RuntimeError(f"layout {LAYOUTS[index]} not active (got {got!r})")

        def at(element: str) -> str:
            r = read_state(state_path)["rects"][element]
            return f"{geo['origin'][0] + r['x'] + 20:.0f} {geo['origin'][1] + r['y'] + r['height'] / 2:.0f}"

        def keys(*seq: str) -> None:
            """Each item: 'x' press+release, '+x' hold, '-x' release."""
            for item in seq:
                if item.startswith("+"):
                    fake(f"kd {K[item[1:]]}")
                elif item.startswith("-"):
                    fake(f"ku {K[item[1:]]}")
                else:
                    fake(f"key {K[item]}")

        def fresh(element: str = "a") -> None:
            host(op="clear")
            fake(f"click {at(element)}")
            wait(state_path, lambda s: s["focus"] == [element])
            host(op="clear")

        def typed(element: str, expected: str, timeout: float = 5.0) -> dict:
            try:
                s = wait(state_path, lambda s: s["values"][element] == expected, timeout=timeout)
            except TimeoutError:
                s = read_state(state_path)
                raise AssertionError(f"{element}={s.get('values', {}).get(element)!r}, expected {expected!r}; log tail {s.get('log', [])[-12:]}")
            time.sleep(0.4)  # nothing late (no double insert)
            s = read_state(state_path)
            if s["values"][element] != expected:
                raise AssertionError(f"late change: {s['values'][element]!r}")
            return s

        def inputs(s: dict) -> list[list]:
            return [e for e in s["log"] if e[0] == "input"]

        def shown():
            wait(state_path, lambda s: s["rects"]["a"], timeout=30)
            g = None
            for _ in range(50):
                g = window_geometry(log, "ui4me input probe", (40, 40, 640, 460))
                if g:
                    break
                time.sleep(0.2)
            if not g:
                raise RuntimeError("KWin does not list the probe window")
            time.sleep(0.5)
            geo["origin"] = window_geometry(log, "ui4me input probe")
            return {"client": geo["origin"]}

        def us_baseline():
            layout(0)
            fresh()
            fake("type Hello, world 1")
            s = typed("a", "Hello, world 1")
            downs = [e for e in s["log"] if e[0] == "keydown"]
            if not downs or downs[0][2] != "ShiftLeft":
                raise AssertionError(f"first keydown {downs[:1]}")
            return {"value": s["values"]["a"], "keydowns": len(downs), "inputs": len(inputs(s))}

        def czech():
            layout(1)
            fresh()
            # number row (+ěščřžýáí): keys 2 5 6 8 -> ě ř ž á; y/z swapped; ů on the semicolon key
            keys("2", "5", "6", "8", "y", "z", "semicolon")
            # dead acute (=) + e -> é ; dead caron (Shift+=) + c -> č ; dead acute + u -> ú
            keys("equal", "e", "+lshift", "equal", "-lshift", "c", "equal", "u")
            # AltGr: q -> \\ , v -> @ , e -> €
            keys("+ralt", "q", "v", "e", "-ralt")
            s = typed("a", "ěřžázyůéčú\\@€")
            per = [e for e in inputs(s)]
            if len(per) != len("ěřžázyůéčú\\@€"):
                raise AssertionError(f"{len(per)} input events for 13 characters: {per}")
            dead = [e for e in s["log"] if e[0] == "keydown" and e[1] == "Dead"]
            return {"value": s["values"]["a"], "inputs": len(per), "dead_keydowns": len(dead)}

        def us_intl():
            layout(2)
            fresh()
            # ' + e -> é ; Shift+' (dead diaeresis) + u -> ü ; ` + a -> à ; ' + space -> ' ; AltGr+s -> ß
            keys("apostrophe", "e", "+lshift", "apostrophe", "-lshift", "u", "grave", "a",
                 "apostrophe", "space", "+ralt", "s", "-ralt")
            s = typed("a", "éüà'ß")
            return {"value": s["values"]["a"], "inputs": len(inputs(s))}

        def german():
            layout(3)
            fresh()
            # y/z swapped, ö ä ü ß, AltGr+q -> @, dead ^ + o -> ô, dead ´ + e -> é
            keys("y", "z", "semicolon", "apostrophe", "lbracket", "minus", "+ralt", "q", "-ralt", "grave", "o", "equal", "e")
            s = typed("a", "zyöäüß@ôé")
            return {"value": s["values"]["a"]}

        def shortcuts():
            layout(1)  # Czech: shortcuts follow the layout's letters (Ctrl+Z is the key labelled Z)
            fresh()
            fake("type abc")
            typed("a", "abc")
            keys("+lctrl", "a", "-lctrl")  # select all: no text
            keys("x")
            typed("a", "x")
            keys("+lctrl", "y", "-lctrl")  # cz: keycode 21 is 'z' -> undo
            s = typed("a", "abc")
            keys("+lctrl", "+lalt", "t", "-lalt", "-lctrl")  # Ctrl+Alt+T: a shortcut, inserts nothing
            keys("+lalt", "d", "-lalt")  # Alt+D: a shortcut, inserts nothing
            s = typed("a", "abc")
            ctrl = [e for e in s["log"] if e[0] == "keydown" and e[3] and e[1] in ("a", "z", "t")]
            return {"value": s["values"]["a"], "ctrl_keydowns": [e[1] for e in ctrl]}

        def repeat():
            layout(0)
            fresh()
            fake(f"kd {K['a']}")
            time.sleep(1.2)
            fake(f"ku {K['a']}")
            time.sleep(0.5)
            s = read_state(state_path)
            value = s["values"]["a"]
            downs = [e for e in s["log"] if e[0] == "keydown" and e[1] == "a"]
            repeats = [e for e in downs if e[6]]
            if len(value) < 3 or set(value) != {"a"} or len(value) != len(downs) or not repeats:
                raise AssertionError(f"value {value!r}, keydowns {len(downs)}, repeats {len(repeats)}")
            return {"chars": len(value), "keydowns": len(downs), "repeat_flagged": len(repeats)}

        def ime_active():
            layout(0)
            fresh()
            for _ in range(50):
                if ime("active").startswith("active"):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("the input method was never activated for a focused text field")
            return {"state": ime("active"), "events": ime("events")}

        def compose(element: str, steps: list[tuple[int, str]], final: str) -> dict:
            for cursor, text in steps:
                if ime(f"preedit {cursor} {text}") != "ok":
                    raise RuntimeError("preedit refused")
                wait(state_path, lambda s, t=text: s["values"][element].endswith(t))
            if ime(f"commit {final}") != "ok":
                raise RuntimeError("commit refused")
            return {}

        def check_once(s: dict, element: str, final: str) -> dict:
            comp = [e for e in s["log"] if e[0].startswith("composition") and e[1] == element]
            starts = [e for e in comp if e[0] == "compositionstart"]
            ends = [e for e in comp if e[0] == "compositionend"]
            commits = [e for e in inputs(s) if e[2] == "insertFromComposition"]
            if len(starts) != 1 or len(ends) != 1 or ends[0][2] != final or len(commits) != 1 or commits[0][3] != final:
                raise AssertionError(f"starts {starts} ends {ends} commits {commits}")
            return {"updates": len(comp) - 2}

        def japanese():
            fresh("a")
            compose("a", [(3, "に"), (6, "にほ"), (9, "にほん"), (6, "日本")], "日本")
            s = typed("a", "日本")
            return {"value": s["values"]["a"], **check_once(s, "a", "日本")}

        def chinese_textarea():
            fresh("t")
            compose("t", [(1, "z"), (5, "zhong"), (6, "中文")], "中文")
            ime("commit ，")  # punctuation with no composition: typed text
            s = typed("t", "中文，")
            plain = [e for e in inputs(s) if e[2] == "insertText"]
            if [e[3] for e in plain] != ["，"]:
                raise AssertionError(f"plain commits {plain}")
            return {"value": s["values"]["t"], **check_once(s, "t", "中文")}

        def korean():
            fresh("a")
            compose("a", [(3, "ㅎ"), (3, "하"), (3, "한")], "한")
            typed("a", "한")
            compose("a", [(3, "ㄱ"), (3, "그"), (3, "글")], "글")
            s = typed("a", "한글")
            ends = [e[2] for e in s["log"] if e[0] == "compositionend"]
            if ends != ["한", "글"]:
                raise AssertionError(f"compositionend {ends}")
            return {"value": s["values"]["a"]}

        def astral():
            fresh("t")
            ime("commit 😀👍🏽 नमस्ते")
            s = typed("t", "😀👍🏽 नमस्ते")
            keys("bs")  # Backspace removes the whole last grapheme cluster? (it removes one code point cluster)
            s = wait(state_path, lambda s: s["values"]["t"] != "😀👍🏽 नमस्ते")
            return {"after_backspace": s["values"]["t"]}

        def cancel():
            fresh("a")
            fake("type ab")
            typed("a", "ab")
            ime("preedit 6 かな")
            wait(state_path, lambda s: s["values"]["a"] == "abかな")
            ime("clear")
            s = typed("a", "ab")
            ends = [e for e in s["log"] if e[0] == "compositionend"]
            if [e[2] for e in ends] != [""]:
                raise AssertionError(f"compositionend {ends}; log {s['log'][-10:]}")
            return {"value": s["values"]["a"]}

        def focus_move_host():
            fresh("a")
            ime("events")
            ime("preedit 15 とうきょう")  # KWin commits this on a reset (commit-on-focus-out IMEs)
            wait(state_path, lambda s: s["values"]["a"] == "とうきょう")
            host(op="focus", element="b")
            try:
                wait(state_path, lambda s: s["focus"] == ["b"])
            except TimeoutError:
                s = read_state(state_path)
                raise AssertionError(f"focus {s.get('focus')} values {s.get('values')} log {s.get('log', [])[-10:]}")
            time.sleep(1.0)
            s = read_state(state_path)
            if s["values"] != {"a": "とうきょう", "b": "", "t": ""}:
                raise AssertionError(f"after focus move {s['values']} (double commit?) log {s['log'][-8:]}")
            imev = ime("events")
            for _ in range(30):
                if ime("active").startswith("active"):
                    break
                time.sleep(0.1)
            compose("b", [(6, "東京")], "東京")
            s = typed("b", "東京")
            if s["values"]["a"] != "とうきょう":
                raise AssertionError(f"a changed: {s['values']}")
            return {"values": s["values"], "ime_events": imev}

        def click_during_preedit():
            fresh("a")
            ime("preedit 9 おおさ")
            wait(state_path, lambda s: s["values"]["a"] == "おおさ")
            fake(f"click {at('t')}")
            wait(state_path, lambda s: s["focus"] == ["t"])
            time.sleep(1.0)
            s = read_state(state_path)
            if s["values"] != {"a": "おおさ", "b": "", "t": ""}:
                raise AssertionError(f"after click {s['values']} log {s['log'][-8:]}")
            fake("type ok")
            s = typed("t", "ok")
            return {"values": s["values"]}

        def host_write_during_preedit():
            fresh("a")
            ime("preedit 6 さく")
            wait(state_path, lambda s: s["values"]["a"] == "さく")
            host(op="set_value", element="a", value="replaced")
            time.sleep(1.0)
            s = read_state(state_path)
            if s["values"]["a"] != "replaced":
                raise AssertionError(f"after host write {s['values']} log {s['log'][-6:]}")
            fake("type X")
            s = typed("a", "replacedX")
            return {"value": s["values"]["a"]}

        def close_during_preedit():
            fresh("a")
            ime("preedit 3 か")
            wait(state_path, lambda s: s["values"]["a"] == "か")
            host(ack=False, op="close")
            code = app.wait(timeout=10)
            if code != 0:
                raise AssertionError(f"probe exit {code}")
            return {"exit": code}

        case("I00-window-shown", shown)
        for name, action in (("K01-us-baseline", us_baseline), ("K02-czech-dead-altgr", czech),
                             ("K03-us-intl-dead", us_intl), ("K04-german", german),
                             ("K05-shortcuts-not-text", shortcuts), ("K06-key-repeat", repeat),
                             ("I01-ime-activates", ime_active), ("I02-japanese-once", japanese),
                             ("I03-chinese-textarea", chinese_textarea), ("I04-korean", korean),
                             ("I05-astral-commit", astral), ("I06-cancel", cancel),
                             ("I07-host-focus-move", focus_move_host), ("I08-click-during-preedit", click_during_preedit),
                             ("I09-host-write-during-preedit", host_write_during_preedit),
                             ("I10-close-during-preedit", close_during_preedit)):
            case(name, action)
    finally:
        if fake:
            try:
                fake.close()
            except Exception:
                pass
        if app and app.poll() is None:
            app.terminate()
            try:
                app.wait(timeout=10)
            except subprocess.TimeoutExpired:
                app.kill()
        reap_private_bus()
        kwin.terminate()
        try:
            kwin.wait(timeout=10)
        except subprocess.TimeoutExpired:
            kwin.kill()
        if log.exists():
            shutil.copy(log, out / "kwin.log")
            log.unlink()
        shutil.rmtree(config, ignore_errors=True)
    status = "passed" if cases and all(c["status"] == "passed" for c in cases) else "failed"
    return {"journey": "input", "status": status, "cases": cases,
            "label": "automated KWin fake_input + scripted zwp_input_method_v1 on a virtual output; not a person"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.inner:
        env = isolated_environment()
        try:
            return subprocess.call(["dbus-run-session", "--", sys.executable, __file__, "--inner", "--out", str(args.out),
                                    "--", *command], env=env)
        finally:
            shutil.rmtree(env["XDG_RUNTIME_DIR"], ignore_errors=True)
    result = journey(args.out.resolve(), command)
    (args.out / "journey.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in result["cases"]:
        print(f"{c['status']:7} {c['id']}  {json.dumps(c.get('details'), ensure_ascii=False)[:200]}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
