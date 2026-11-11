-- UI4ME Core host binding for LuaJIT (FFI only, no compiled glue, no external rocks).
--
--   local ui4me = require("ui4me")
--   local app = ui4me.App{ backend = "native", app_id = "org.example.notes" }
--   local win = app:open('<button id="go">Go</button><p id="out"></p>', { title = "Hi" })
--   win:on("click", function(ev) win:set_text("out", "clicked") end, { element = "go" })
--   app:run()
--   app:close()
--
-- It binds the stable C ABI 1 (include/ui4me.h) and mirrors the core subset of the Python
-- binding (bindings/python/src/ui4me/app.py). Finding the native library, in order:
--   1. env UI4ME_NATIVE_LIB  - absolute path of libui4me_core.so (Linux) / ui4me_core.dll (Windows),
--      for example target/debug/libui4me_core.so from a repository build or the file inside a
--      Core release archive / wheel;
--   2. next to this file, then in <this dir>/native/ (ui4me_core.dll / libui4me_core.so).
--
-- THREADING. Lua states are single-threaded and so is the ABI: App.new / :open / every window
-- command / :run / :close must run on the one OS thread that created the App (the "owner");
-- calling them elsewhere is a native error 3 (wrong thread). Callbacks (events, timers, posts)
-- are invoked by the native loop only on that thread, inside :run() (or inside the command
-- that provoked them, e.g. check_validity). The ABI functions ui4me_session_post / _stop /
-- _complete are thread-safe, but a Lua state must never run on a second OS thread, so this
-- binding does not expose them to other Lua threads. Use :post from the owner thread (it is
-- queued and runs later, in order) and :timer; see tests/lua for a native-thread stop test.
--
-- CALLBACK LIFETIME. One FFI callback object is created per App and is anchored in a module
-- table until :close() frees it (cb:free()). A Lua error inside a handler is caught with xpcall
-- inside the callback (it never unwinds through C), recorded, the session is stopped, and the
-- first error is re-raised from :run() once the native loop has returned.
--
-- ERRORS. Failures are raised as tables with fields `code` (ABI status 1..9, or -1 for
-- binding-side misuse such as a closed window), `name` and `message`; tostring() works on them.
-- Use ui4me.is_error(e). JSON: ui4me.json (null in objects decodes to nil; use json.array{}
-- to force an empty array; commands go through :command(tbl)).

local ffi = require("ffi")
local bit = require("bit")

local M = {}
M.ABI = 1

-- ---------------------------------------------------------------------------------------
-- JSON (small, strict enough for the ABI's UTF-8 documents; original code, MIT like Core)
-- ---------------------------------------------------------------------------------------
local json = {}
M.json = json
local array_mt = { __jsontype = "array" }
json.null = setmetatable({}, { __tostring = function() return "null" end })

function json.array(t) return setmetatable(t or {}, array_mt) end

local escapes = { ['"'] = '\\"', ["\\"] = "\\\\", ["\b"] = "\\b", ["\f"] = "\\f",
                  ["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t" }
local function escape_char(c)
    return escapes[c] or string.format("\\u%04x", c:byte())
end

local function is_array(t)
    if getmetatable(t) == array_mt then return true end
    local n = 0
    for k in pairs(t) do
        if type(k) ~= "number" or k < 1 or k % 1 ~= 0 then return false end
        n = n + 1
    end
    return n > 0 and n == #t
end

local function encode(v, out, depth)
    local tv = type(v)
    if tv == "string" then
        out[#out + 1] = '"' .. v:gsub('[%c"\\]', escape_char) .. '"'
    elseif tv == "number" then
        if v ~= v or v == math.huge or v == -math.huge then error("JSON cannot encode NaN or infinity", 0) end
        if v % 1 == 0 and v > -2 ^ 53 and v < 2 ^ 53 then out[#out + 1] = string.format("%d", v)
        else out[#out + 1] = string.format("%.17g", v) end
    elseif tv == "boolean" then
        out[#out + 1] = v and "true" or "false"
    elseif tv == "nil" or v == json.null then
        out[#out + 1] = "null"
    elseif tv == "cdata" then
        encode(tonumber(v), out, depth)
    elseif tv == "table" then
        if depth > 64 then error("JSON nesting too deep", 0) end
        if is_array(v) then
            out[#out + 1] = "["
            for i = 1, #v do
                if i > 1 then out[#out + 1] = "," end
                encode(v[i], out, depth + 1)
            end
            out[#out + 1] = "]"
        else
            out[#out + 1] = "{"
            local first = true
            for k, val in pairs(v) do
                if type(k) ~= "string" then error("JSON object keys must be strings", 0) end
                if not first then out[#out + 1] = "," end
                first = false
                out[#out + 1] = '"' .. k:gsub('[%c"\\]', escape_char) .. '":'
                encode(val, out, depth + 1)
            end
            out[#out + 1] = "}"
        end
    else
        error("JSON cannot encode a " .. tv, 0)
    end
end

function json.encode(v)
    local out = {}
    encode(v, out, 0)
    return table.concat(out)
end

local function utf8_encode(cp)
    if cp < 0x80 then return string.char(cp)
    elseif cp < 0x800 then return string.char(0xC0 + bit.rshift(cp, 6), 0x80 + bit.band(cp, 0x3F))
    elseif cp < 0x10000 then
        return string.char(0xE0 + bit.rshift(cp, 12), 0x80 + bit.band(bit.rshift(cp, 6), 0x3F), 0x80 + bit.band(cp, 0x3F))
    end
    return string.char(0xF0 + bit.rshift(cp, 18), 0x80 + bit.band(bit.rshift(cp, 12), 0x3F),
        0x80 + bit.band(bit.rshift(cp, 6), 0x3F), 0x80 + bit.band(cp, 0x3F))
end

local function decode_error(s, i, what)
    error(string.format("JSON decode error at byte %d: %s", i, what), 0)
end

local decode_value
local function skip(s, i) return s:find("[^ \t\r\n]", i) or #s + 1 end

local function decode_string(s, i)
    local parts, j = {}, i + 1
    while true do
        local k = s:find('["\\%c]', j)
        if not k then decode_error(s, i, "unterminated string") end
        local c = s:sub(k, k)
        if c == '"' then
            parts[#parts + 1] = s:sub(j, k - 1)
            return table.concat(parts), k + 1
        elseif c == "\\" then
            parts[#parts + 1] = s:sub(j, k - 1)
            local e = s:sub(k + 1, k + 1)
            local simple = { ['"'] = '"', ["\\"] = "\\", ["/"] = "/", b = "\b", f = "\f", n = "\n", r = "\r", t = "\t" }
            if simple[e] then
                parts[#parts + 1] = simple[e]
                j = k + 2
            elseif e == "u" then
                local hex = s:match("^%x%x%x%x", k + 2)
                if not hex then decode_error(s, k, "bad \\u escape") end
                local cp = tonumber(hex, 16)
                j = k + 6
                if cp >= 0xD800 and cp < 0xDC00 then
                    local low = s:match("^\\u(%x%x%x%x)", j)
                    low = low and tonumber(low, 16)
                    if low and low >= 0xDC00 and low < 0xE000 then
                        cp = 0x10000 + (cp - 0xD800) * 0x400 + (low - 0xDC00)
                        j = j + 6
                    else
                        cp = 0xFFFD
                    end
                elseif cp >= 0xDC00 and cp < 0xE000 then
                    cp = 0xFFFD
                end
                parts[#parts + 1] = utf8_encode(cp)
            else
                decode_error(s, k, "bad escape")
            end
        else
            decode_error(s, k, "control character in string")
        end
    end
end

function decode_value(s, i, depth)
    if depth > 128 then decode_error(s, i, "nesting too deep") end
    i = skip(s, i)
    local c = s:sub(i, i)
    if c == "{" then
        local obj = {}
        i = skip(s, i + 1)
        if s:sub(i, i) == "}" then return obj, i + 1 end
        while true do
            if s:sub(i, i) ~= '"' then decode_error(s, i, "object key expected") end
            local key
            key, i = decode_string(s, i)
            i = skip(s, i)
            if s:sub(i, i) ~= ":" then decode_error(s, i, "':' expected") end
            local val
            val, i = decode_value(s, i + 1, depth + 1)
            obj[key] = val -- null decodes to nil: the key is simply absent
            i = skip(s, i)
            local d = s:sub(i, i)
            if d == "}" then return obj, i + 1 end
            if d ~= "," then decode_error(s, i, "',' or '}' expected") end
            i = skip(s, i + 1)
        end
    elseif c == "[" then
        local arr, n = json.array({}), 0
        i = skip(s, i + 1)
        if s:sub(i, i) == "]" then return arr, i + 1 end
        while true do
            local val
            val, i = decode_value(s, i, depth + 1)
            n = n + 1
            if val == nil then val = json.null end
            arr[n] = val
            i = skip(s, i)
            local d = s:sub(i, i)
            if d == "]" then return arr, i + 1 end
            if d ~= "," then decode_error(s, i, "',' or ']' expected") end
            i = i + 1
        end
    elseif c == '"' then
        return decode_string(s, i)
    elseif s:sub(i, i + 3) == "true" then return true, i + 4
    elseif s:sub(i, i + 4) == "false" then return false, i + 5
    elseif s:sub(i, i + 3) == "null" then return nil, i + 4
    end
    local num = s:match("^-?%d+%.?%d*[eE]?[+-]?%d*", i)
    if not num or num == "" or not tonumber(num) then decode_error(s, i, "unexpected character") end
    return tonumber(num), i + #num
end

function json.decode(s)
    if type(s) ~= "string" then error("JSON decode needs a string", 0) end
    local v, i = decode_value(s, 1, 0)
    if skip(s, i) <= #s then decode_error(s, i, "trailing data") end
    return v
end

-- ---------------------------------------------------------------------------------------
-- Errors
-- ---------------------------------------------------------------------------------------
local STATUS = { [-1] = "binding", [1] = "invalid_argument", [2] = "lifecycle", [3] = "wrong_thread",
                 [4] = "stale_handle", [5] = "resource_limit", [6] = "native_runtime", [7] = "callback",
                 [8] = "poisoned", [9] = "io" }
local Error = {}
Error.__index = Error
Error.__tostring = function(e) return string.format("ui4me error %d (%s): %s", e.code, e.name, e.message) end
M.Error = Error

local function fail(message, code)
    code = code or -1
    error(setmetatable({ code = code, name = STATUS[code] or "unknown", message = message }, Error), 0)
end

function M.is_error(e) return getmetatable(e) == Error end

-- ---------------------------------------------------------------------------------------
-- Native library
-- ---------------------------------------------------------------------------------------
ffi.cdef [[
typedef int32_t (*ui4me_callback)(uint64_t session, const char *event_json, void *user);
uint32_t ui4me_abi_version(void);
const char *ui4me_build_info(void);
const char *ui4me_last_error(void);
int32_t ui4me_session_create(const char *config_json, ui4me_callback callback, void *user, uint64_t *out_session);
int32_t ui4me_session_command(uint64_t session, const char *command_json, const char **out_json);
int32_t ui4me_session_run(uint64_t session);
int32_t ui4me_session_post(uint64_t session, uint64_t token);
int32_t ui4me_session_stop(uint64_t session);
int32_t ui4me_session_complete(uint64_t session, uint64_t token);
int32_t ui4me_session_destroy(uint64_t session);
]]

local is_windows = ffi.os == "Windows"
local lib_name = is_windows and "ui4me_core.dll" or "libui4me_core.so"

local function file_exists(path)
    local f = io.open(path, "rb")
    if f then f:close() return true end
    return false
end

local function is_absolute(p)
    return p:sub(1, 1) == "/" or p:match("^%a:[\\/]") ~= nil or p:sub(1, 2) == "\\\\"
end

local function module_dir()
    local src = debug.getinfo(1, "S").source
    if src:sub(1, 1) == "@" then
        return (src:sub(2):match("^(.*)[/\\][^/\\]*$")) or "."
    end
    return "."
end

function M.native_path()
    local override = os.getenv("UI4ME_NATIVE_LIB")
    if override and override ~= "" then
        if not is_absolute(override) then fail("UI4ME_NATIVE_LIB must be an absolute file path") end
        if not file_exists(override) then fail("Native runtime not found: " .. override) end
        return override
    end
    local dir = module_dir()
    local sep = is_windows and "\\" or "/"
    for _, candidate in ipairs { dir .. sep .. lib_name, dir .. sep .. "native" .. sep .. lib_name } do
        if file_exists(candidate) then
            if not is_absolute(candidate) then
                -- ffi.load needs a path the loader will not search the library path for.
                candidate = (is_windows and ".\\" or "./") .. candidate
                if candidate:sub(1, 4) == "././" then candidate = candidate:sub(3) end
            end
            return candidate
        end
    end
    fail("Native runtime " .. lib_name .. " not found. Set UI4ME_NATIVE_LIB to the absolute path of "
        .. lib_name .. " from a UI4ME Core build or release, or place it next to ui4me.lua.")
end

local C, native_file
local function native()
    if C then return C end
    native_file = M.native_path()
    local ok, lib = pcall(ffi.load, native_file)
    if not ok then fail("Cannot load " .. native_file .. ": " .. tostring(lib)) end
    if lib.ui4me_abi_version() ~= 1 then fail("Unsupported ui4me ABI; this binding requires ABI 1") end
    local info = json.decode(ffi.string(lib.ui4me_build_info()))
    if info.product ~= "ui4me" then fail("Native product does not match ui4me") end
    C = lib
    return C
end

function M.build_info()
    local lib = native()
    local info = json.decode(ffi.string(lib.ui4me_build_info()))
    info.abi = tonumber(lib.ui4me_abi_version())
    info.library_path = native_file
    return info
end

local function check(status)
    if status ~= 0 then
        local msg = C.ui4me_last_error()
        local text = msg ~= nil and ffi.string(msg) or "Native operation failed"
        local ok, doc = pcall(json.decode, text)
        if ok and type(doc) == "table" and doc.message then text = doc.message end
        fail(text, tonumber(status))
    end
end

-- Roots callback objects (and their App) so the GC cannot free a callback the native side holds.
local live_apps = {}

-- ---------------------------------------------------------------------------------------
-- Futures, subscriptions, timers
-- ---------------------------------------------------------------------------------------
local Future = {}
Future.__index = Future

--- True once the posted function ran or was cancelled.
function Future:done() return self._state ~= "pending" end
function Future:cancelled() return self._state == "cancelled" end
--- Cancel work that has not run yet. Returns false when it already ran.
function Future:cancel()
    if self._state == "pending" then self._state = "cancelled" return true end
    return self._state == "cancelled"
end
--- The outcome. Lua cannot block (a wait on the owner thread would starve the loop), so this
--- raises when the work has not run yet; call it after :run() returns or from a later callback.
function Future:result()
    if self._state == "pending" then fail("posted work has not run yet; the owner loop must run it") end
    if self._state == "cancelled" then fail("posted work was cancelled") end
    if self._state == "failed" then error(self._error, 0) end
    return self._value
end

local Subscription = {}
Subscription.__index = Subscription
function Subscription:close() self._app:_unsubscribe(self._entry) end

local Timer = {}
Timer.__index = Timer
function Timer:cancel()
    local app = self._app
    if app._timers[self.token] then
        if (app._state == "created" or app._state == "running") and not app._stopping then
            app:_command { op = "cancel_timer", token = self.token }
        end
        app._timers[self.token] = nil
    end
end

-- ---------------------------------------------------------------------------------------
-- Window
-- ---------------------------------------------------------------------------------------
local Window = {}
Window.__index = Window

function Window:_command(op, args)
    if self.closed then fail("Window is closed") end
    local cmd = { op = op, window = self.id }
    if args then for k, v in pairs(args) do cmd[k] = v end end
    return self._app:_command(cmd)
end

--- Send any window command table (`window` is filled in). Returns the decoded reply.
function Window:command(tbl)
    if type(tbl) ~= "table" or type(tbl.op) ~= "string" then fail("command needs a table with an `op` string") end
    return self:_command(tbl.op, tbl)
end

--- Subscribe to a window event. opts.element restricts it to that element or its descendants.
function Window:on(event, fn, opts)
    if self.closed then fail("Window is closed") end
    return self._app:_subscribe(event, fn, self.id, opts and opts.element)
end

function Window:set_text(element, text) self:_command("set_text", { element = element, text = text }) end
function Window:get_text(element) return self:_command("get_text", { element = element }).text end
function Window:set_value(element, value) self:_command("set_value", { element = element, value = value }) end
function Window:get_value(element) return self:_command("get_value", { element = element }).value end
function Window:get_checked(element) return self:_command("get_checked", { element = element }).checked end
function Window:set_checked(element, checked)
    if type(checked) ~= "boolean" then fail("checked must be a boolean", 1) end
    self:_command("set_checked", { element = element, checked = checked })
end
function Window:set_attribute(element, name, value) self:_command("set_attribute", { element = element, name = name, value = value }) end
function Window:get_attribute(element, name) return self:_command("get_attribute", { element = element, name = name }).value end
function Window:get_attributes(element) return self:_command("get_attributes", { element = element }).attributes end
function Window:remove_attribute(element, name) self:_command("remove_attribute", { element = element, name = name }) end
function Window:has_element(element) return self:_command("has_element", { element = element }).exists end
function Window:add_class(element, name) self:_command("add_class", { element = element, name = name }) end
function Window:remove_class(element, name) self:_command("remove_class", { element = element, name = name }) end
function Window:focus(element) self:_command("focus", { element = element }) end
--- Replace the children of `element` with a validated fragment (rejection changes nothing).
function Window:set_html(element, html) self:_command("replace_children_html", { element = element, html = html }) end
--- position: beforebegin | afterbegin | beforeend | afterend
function Window:insert_html(element, position, html)
    self:_command("insert_html", { element = element, position = position, html = html })
end
function Window:append_html(element, html) self:insert_html(element, "beforeend", html) end
function Window:prepend_html(element, html) self:insert_html(element, "afterbegin", html) end
function Window:append_text(element, text) self:_command("append_text", { element = element, text = text }) end
function Window:remove_element(element) self:_command("remove_element", { element = element }) end
function Window:move_element(element, target, position)
    self:_command("move_element", { element = element, target = target, position = position or "beforeend" })
end
--- Keep at most `keep` element children; from = "start" (default, drop oldest) or "end".
function Window:trim_children(element, keep, from)
    self:_command("trim_children", { element = element, keep = keep, from = from or "start" })
end
--- IDs of identified elements matching a CSS selector, in document order.
function Window:query(selector, limit)
    return self:_command("query", { selector = selector, limit = limit or 1024 }).elements
end
--- Border box {x,y,width,height} in viewport CSS px, or nil.
function Window:get_rect(element) return self:_command("get_rect", { element = element }).rect end
--- Atomic list of DOM operations.
function Window:batch(ops) self:_command("batch", { ops = json.array(ops) }) end
function Window:set_title(title) self:_command("set_title", { title = title }) end
function Window:resize(width, height) self:_command("resize", { width = width, height = height }) end
function Window:diagnostics() return self:_command("diagnostics") end
function Window:close() self:_command("close") end

-- ---------------------------------------------------------------------------------------
-- App
-- ---------------------------------------------------------------------------------------
local App = {}
App.__index = App
M.App_class = App

local MAX_COMMAND = 2 * 1024 * 1024

function App:_active()
    if self._state ~= "created" and self._state ~= "running" or self._stopping then
        fail("Application session is stopping or terminal; create a fresh App")
    end
end

function App:_raw_command(cmd)
    local payload = json.encode(cmd)
    if #payload > MAX_COMMAND then fail("Command exceeds 2 MiB", 1) end
    check(C.ui4me_session_command(self._session, payload, self._out))
    local ptr = self._out[0]
    local reply = ptr ~= nil and ffi.string(ptr) or "{}"
    return json.decode(reply)
end

function App:_command(cmd)
    self:_active()
    return self:_raw_command(cmd)
end

--- Send any session command table and return the decoded reply (escape hatch for ops this
--- binding has no named method for).
-- Native calls that may re-enter Lua through the FFI callback (commands such as check_validity,
-- run, destroy) must not be part of a JIT-compiled trace: LuaJIT panics with "bad callback"
-- when a callback fires from a compiled C call. Keep these entry points interpreted.
jit.off(App._raw_command)

function App:command(tbl)
    if type(tbl) ~= "table" or type(tbl.op) ~= "string" then fail("command needs a table with an `op` string") end
    return self:_command(tbl)
end

function App:_subscribe(event, fn, window, element)
    self:_active()
    if type(fn) ~= "function" then fail("handler must be a function", 1) end
    if self._nhandlers >= 512 then fail("At most 512 subscriptions may be active", 5) end
    local entry = { event = event, window = window, element = element, fn = fn }
    self._handlers[#self._handlers + 1] = entry
    self._nhandlers = self._nhandlers + 1
    return setmetatable({ _app = self, _entry = entry }, Subscription)
end

function App:_unsubscribe(entry)
    if entry.removed then return end
    entry.removed = true
    for i, e in ipairs(self._handlers) do
        if e == entry then
            table.remove(self._handlers, i)
            self._nhandlers = self._nhandlers - 1
            break
        end
    end
end

function App:on(event, fn) return self:_subscribe(event, fn, nil, nil) end

function App:_next_token()
    self._token = self._token + 1
    return self._token
end

local function opened(app, reply)
    local w = setmetatable({ _app = app, id = reply.window, closed = false }, Window)
    app._windows[w.id] = w
    return w
end

--- Open an HTML document. opts: title, width, height, base_path (needed for relative assets).
function App:open(html, opts)
    opts = opts or {}
    local cmd = { op = "open", title = opts.title or "ui4me", html = html,
                  width = opts.width or 640, height = opts.height or 480 }
    if opts.base_path then cmd.base_path = opts.base_path end
    return opened(self, self:_command(cmd))
end

--- Load a document from a file path; assets resolve against the file's directory.
function App:open_file(path, opts)
    opts = opts or {}
    return opened(self, self:_command { op = "open_file", path = path, title = opts.title or "ui4me",
                                         width = opts.width or 640, height = opts.height or 480 })
end

--- Fire fn(event) after `milliseconds`; opts.repeat = true repeats until cancelled.
function App:timer(milliseconds, fn, opts)
    self:_active()
    if type(fn) ~= "function" then fail("handler must be a function", 1) end
    local repeating = opts and opts["repeat"] or false
    local token = self:_next_token()
    self:_command { op = "timer", token = token, milliseconds = milliseconds, ["repeat"] = repeating }
    self._timers[token] = { fn = fn, repeating = repeating }
    return setmetatable({ _app = self, token = token }, Timer)
end

--- Queue fn() to run on the owner thread inside the loop, in post order. Returns a Future.
--- The native post queue is bounded; a full queue raises resource_limit (code 5).
function App:post(fn)
    if type(fn) ~= "function" then fail("callback must be a function", 1) end
    if self._state ~= "created" and self._state ~= "running" or self._stopping then
        fail("Application is no longer accepting work")
    end
    if self._npending >= 512 then fail("Deferred work queue is full", 5) end
    local future = setmetatable({ _state = "pending" }, Future)
    local token = self:_next_token()
    self._pending[token] = { future = future, fn = fn }
    self._npending = self._npending + 1
    local status = C.ui4me_session_post(self._session, token)
    if status ~= 0 then
        self._pending[token] = nil
        self._npending = self._npending - 1
        check(status)
    end
    return future
end

function App:stop()
    if self._state == "stopped" or self._state == "closed" then return end
    self._stopping = true
    check(C.ui4me_session_stop(self._session))
end

function App:_record_error(err)
    if self._callback_error == nil then self._callback_error = err end
    self._stopping = true
    C.ui4me_session_stop(self._session)
end

local function traceback(err)
    if type(err) == "string" then return debug.traceback(err, 2) end
    return err
end

local function has_path(path, element)
    if type(path) ~= "table" then return false end
    for _, id in ipairs(path) do if id == element then return true end end
    return false
end

function App:_dispatch(raw)
    local event = json.decode(raw)
    local kind = event.type
    if kind == "stopped" then
        self._stopping = true
        self._state = "stopped"
    elseif kind == "closed" then
        local w = self._windows[event.window]
        self._windows[event.window] = nil
        if w then w.closed = true end
    elseif kind == "post" then
        local entry = self._pending[event.token]
        if entry then
            self._pending[event.token] = nil
            self._npending = self._npending - 1
            local f = entry.future
            if f._state == "pending" then
                local ok, res = xpcall(entry.fn, traceback)
                if ok then f._state, f._value = "succeeded", res
                else f._state, f._error = "failed", res end
            end
        end
    elseif kind == "timer" then
        local t = self._timers[event.token]
        if t then
            if not t.repeating then self._timers[event.token] = nil end
            t.fn(event)
        end
    end
    local veto = false
    local snapshot = { unpack(self._handlers) }
    for _, h in ipairs(snapshot) do
        if not h.removed and h.event == kind and (h.window == nil or h.window == event.window)
            and (h.element == nil or h.element == event.element or has_path(event.path, h.element)) then
            if h.fn(event) == false and kind == "close_requested" then veto = true end
        end
    end
    if kind == "closed" then
        for _, h in ipairs(snapshot) do
            if h.window ~= nil and h.window == event.window then self:_unsubscribe(h) end
        end
    end
    return veto and 1 or 0
end

--- The native entry point. Never raises and never yields; a Lua error is recorded, the
--- session is stopped and :run() re-raises it. Exposed so tests can feed synthetic events.
function App:_on_native_event(raw)
    local ok, result = xpcall(self._dispatch, traceback, self, raw)
    if ok then return result end
    self:_record_error(result)
    return -1
end

--- Run the native loop on the owner thread until :stop() (or the last window closes, per the
--- backend). Re-raises the first error that a handler threw.
function App:run()
    if self._state ~= "created" then fail("Application is already running") end
    self._state = "running"
    self._run_active = true
    local status = C.ui4me_session_run(self._session)
    self._state = "stopped"
    self._run_active = false
    local pending = self._pending
    self._pending, self._npending = {}, 0
    for _, entry in pairs(pending) do entry.future:cancel() end
    self._timers = {}
    for _, w in pairs(self._windows) do w.closed = true end
    self._windows = {}
    self._handlers, self._nhandlers = {}, 0
    if self._callback_error ~= nil then
        local err = self._callback_error
        self._callback_error = nil
        error(err, 0)
    end
    check(status)
end

jit.off(App.run)

--- Native session statistics (allowed after the session stopped).
function App:stats()
    if self._state == "closed" then fail("Application has been disposed") end
    return self:_raw_command { op = "stats" }
end

function App:capabilities() return self:_command { op = "capabilities" } end

--- Destroy the session and free the callback. Idempotent. Call after :run() returned.
function App:close()
    if self._state == "closed" then return end
    if self._run_active then fail("Call stop() during run(); close the App after run() returns") end
    check(C.ui4me_session_destroy(self._session))
    self._state, self._stopping = "closed", true
    for _, entry in pairs(self._pending) do entry.future:cancel() end
    self._pending, self._npending = {}, 0
    self._handlers, self._nhandlers, self._timers = {}, 0, {}
    for _, w in pairs(self._windows) do w.closed = true end
    self._windows = {}
    live_apps[self._session_key] = nil
    if self._cb then
        self._cb:free()
        self._cb = nil
    end
end

jit.off(App.close)

--- Create an application session. opts: backend "native" (default) or "headless", app_id.
function M.App(opts)
    opts = opts or {}
    local backend = opts.backend or "native"
    if backend ~= "native" and backend ~= "headless" then fail("backend must be native or headless", 1) end
    local lib = native()
    local self = setmetatable({
        _state = "created", _stopping = false, _run_active = false, _token = 0,
        _handlers = {}, _nhandlers = 0, _timers = {}, _pending = {}, _npending = 0,
        _windows = {}, _out = ffi.new("const char*[1]"), _backend = backend,
    }, App)
    -- The callback closes over `self`; the native side never sees a Lua error.
    self._cb = ffi.cast("ui4me_callback", function(_, raw, _)
        if self._state == "closed" then return 0 end
        return self:_on_native_event(ffi.string(raw))
    end)
    local id = ffi.new("uint64_t[1]")
    local config = json.encode { backend = backend, app_id = opts.app_id or "org.ui4me.app" }
    local status = lib.ui4me_session_create(config, self._cb, nil, id)
    if status ~= 0 then
        self._cb:free()
        self._cb = nil
        check(status)
    end
    self._session = id[0]
    self._session_key = tostring(id[0])
    live_apps[self._session_key] = self
    return self
end

function App:session_id() return tostring(self._session) end

return M
