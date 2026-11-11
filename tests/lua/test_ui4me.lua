-- Contract tests for the LuaJIT binding against the real native library (headless backend).
--
--   UI4ME_NATIVE_LIB=$PWD/target/debug/libui4me_core.so \
--       build/luajit/src/luajit tests/lua/test_ui4me.lua
--
-- Exit status 0 only when every test passed.
local here = (debug.getinfo(1, "S").source:sub(2):match("^(.*)[/\\][^/\\]*$")) or "."
package.path = here .. "/../../bindings/lua/?.lua;" .. package.path
local ffi = require("ffi")
local ui4me = require("ui4me")
local json = ui4me.json

io.stdout:setvbuf("no")
local passed, failed, names = 0, 0, {}
local only = os.getenv("UI4ME_LUA_ONLY")
local function test(name, fn)
    if only then local hit = false for pat in only:gmatch("[^|]+") do if name:find(pat, 1, true) then hit = true end end if not hit then return end end
    local ok, err = xpcall(fn, function(e) return tostring(e) .. "\n" .. debug.traceback("", 2) end)
    if ok then passed = passed + 1; print("ok      " .. name)
    else failed = failed + 1; names[#names + 1] = name; print("FAILED  " .. name .. "\n" .. err) end
end
local function eq(a, b, msg)
    if a ~= b then error(string.format("%s: expected %s, got %s", msg or "eq", tostring(b), tostring(a)), 2) end
end
local function truthy(v, msg) if not v then error(msg or "expected truthy", 2) end end
local function raises(fn, pattern)
    local ok, err = pcall(fn)
    if ok then error("expected an error", 2) end
    if pattern and not tostring(err):find(pattern) then error("error did not match " .. pattern .. ": " .. tostring(err), 2) end
    return err
end
local function headless() return ui4me.App { backend = "headless" } end
-- Run a session until its first "started" event, then stop it.
local function run_started(app, fn)
    app:on("started", function() if fn then fn() end app:stop() end)
    app:run()
end

test("json round trip, escapes, unicode and surrogates", function()
    local s = json.encode { text = 'a"b\\c\n\t\1', n = 42, f = 1.5, t = true, list = { 1, 2, 3 }, empty = json.array() }
    local d = json.decode(s)
    eq(d.text, 'a"b\\c\n\t\1'); eq(d.n, 42); eq(d.f, 1.5); eq(d.t, true); eq(#d.list, 3); eq(#d.empty, 0)
    eq(json.decode('"\\u0159\\ud83d\\ude00"'), "\xC5\x99\xF0\x9F\x98\x80")
    eq(json.decode('"P\xC5\x99\xC3\xADli\xC5\xA1"'), "P\xC5\x99\xC3\xADli\xC5\xA1")
    eq(json.encode("\xC5\x99"), '"\xC5\x99"')
    eq(json.decode('{"a":null,"b":[1,null]}').a, nil)
    eq(json.decode('{"a":null,"b":[1,null]}').b[2], json.null)
    eq(json.encode({}), "{}"); eq(json.encode(json.array()), "[]")
    raises(function() json.decode('{"a":') end, "JSON decode error")
    raises(function() json.decode('[1] x') end, "trailing")
    raises(function() json.encode(0 / 0) end, "NaN")
end)

test("build info and ABI 1", function()
    local info = ui4me.build_info()
    eq(info.abi, 1); eq(info.product, "ui4me"); truthy(info.library_path)
end)

test("lifecycle: started, stopped, terminal state, double close", function()
    local app = headless()
    local seen = {}
    app:on("started", function() seen[#seen + 1] = "started"; app:stop() end)
    app:on("stopped", function() seen[#seen + 1] = "stopped" end)
    app:run()
    eq(table.concat(seen, ","), "started,stopped")
    raises(function() app:run() end, "already running")
    raises(function() app:open("<p>x</p>") end, "terminal")
    truthy(type(app:stats()) == "table")
    app:close(); app:close()
    raises(function() app:stats() end, "disposed")
end)

test("many sessions release their callback slots", function()
    -- LuaJIT has a few hundred callback slots; a leak would exhaust them.
    for _ = 1, 700 do
        local app = headless()
        app:close()
    end
    local app = headless()
    run_started(app)
    app:close()
end)

test("close during run is refused, then works after run returns", function()
    local app = headless()
    local err
    run_started(app, function() local ok, e = pcall(app.close, app); err = e end)
    truthy(tostring(err):find("stop%(%) during run"), tostring(err))
    app:close()
end)

test("document commands and unicode", function()
    local app = headless()
    local w = app:open('<input id="v" value="A"><p id="p">x</p><input id="c" type="checkbox"><div id="d"></div>')
    w:set_text("p", "P\xC5\x99\xC3\xADli\xC5\xA1")
    eq(w:get_text("p"), "P\xC5\x99\xC3\xADli\xC5\xA1")
    w:set_value("v", "\xC5\xBElu\xC5\xA5")
    eq(w:get_value("v"), "\xC5\xBElu\xC5\xA5")
    w:set_checked("c", true); eq(w:get_checked("c"), true)
    raises(function() w:set_checked("c", "yes") end, "boolean")
    w:set_attribute("p", "title", "t"); eq(w:get_attribute("p", "title"), "t")
    eq(w:get_attribute("p", "nope"), nil)
    w:remove_attribute("p", "title"); eq(w:get_attribute("p", "title"), nil)
    w:append_html("d", '<span id="s1">1</span>'); w:append_html("d", '<span id="s2">2</span>')
    w:prepend_html("d", '<span id="s0">0</span>')
    eq(table.concat(w:query("#d > span"), ","), "s0,s1,s2")
    w:set_html("d", '<b id="only">o</b>')
    eq(table.concat(w:query("#d > *"), ","), "only")
    eq(w:has_element("only"), true); eq(w:has_element("s1"), false)
    w:batch { { op = "set_text", element = "p", text = "batched" }, { op = "add_class", element = "p", name = "k" } }
    eq(w:get_text("p"), "batched")
    local r = w:get_rect("p")
    truthy(r and r.width > 0 and r.height > 0, "rect")
    w:set_title("renamed"); w:resize(300, 200)
    w:move_element("only", "p", "afterend")
    eq(w:query("#only")[1], "only")
    w:remove_element("only"); eq(w:has_element("only"), false)
    truthy(type(w:diagnostics()) == "table")
    local reply = w:command { op = "get_text", element = "p" }
    eq(reply.text, "batched")
    app:close()
end)

test("errors carry code, name and message", function()
    local app = headless()
    local w = app:open('<p id="p">x</p>')
    local e = raises(function() w:set_text("missing", "x") end)
    truthy(ui4me.is_error(e), "error object"); truthy(e.code >= 1 and e.code <= 9, "status code " .. tostring(e.code))
    truthy(#e.message > 0); truthy(tostring(e):find("ui4me error"))
    local e2 = raises(function() app:command { op = "no_such_operation" } end)
    truthy(ui4me.is_error(e2) and e2.code == 1, "unknown op is invalid_argument")
    eq(e2.name, "invalid_argument")
    raises(function() w:set_attribute("p", "onclick", "x()") end) -- active content stays rejected
    raises(function() ui4me.App { backend = "bogus" } end, "backend")
    raises(function() app:command("nope") end, "table")
    raises(function() app:on("started", 5) end, "function")
    -- A rejected fragment changes nothing.
    w:set_html("p", "<i>ok</i>")
    raises(function() w:set_html("p", '<script>1</script>') end)
    eq(w:get_text("p"), "ok")
    app:close()
end)

test("stale window after the session stopped", function()
    local app = headless()
    local w = app:open('<p id="x">T</p>')
    run_started(app)
    truthy(w.closed, "window marked closed")
    raises(function() w:set_text("x", "stale") end, "closed")
    raises(function() w:on("click", function() end) end, "closed")
    app:close()
end)

test("closed window command is rejected, window event and visible state", function()
    local app = headless()
    local w = app:open("<p>w</p>")
    local seen = {}
    w:on("closed", function() seen[#seen + 1] = w.closed end)
    app:on("started", function() w:close() end)
    app:on("closed", function() app:stop() end)
    app:run()
    eq(#seen, 1); eq(seen[1], true)
    raises(function() w:close() end, "closed")
    app:close()
end)

test("native element events: invalid, element filter, ancestor path", function()
    local app = headless()
    local w = app:open('<form id="f"><input id="n" required><input id="m" required></form>')
    local on_n, on_form, other = {}, {}, {}
    w:on("invalid", function(e) on_n[#on_n + 1] = e.element end, { element = "n" })
    w:on("invalid", function(e) on_form[#on_form + 1] = e.element end)
    w:on("invalid", function() other[#other + 1] = 1 end, { element = "zzz" })
    local result = w:command { op = "check_validity", element = "f" }
    eq(result.valid, false); eq(result.count, 2)
    eq(table.concat(on_n, ","), "n"); eq(table.concat(on_form, ","), "n,m"); eq(#other, 0)
    -- Synthetic bubbling event: an ancestor in `path` matches the element filter exactly once.
    local seen = {}
    w:on("click", function(e) seen[#seen + 1] = e.element end, { element = "button" })
    w:on("click", function() seen[#seen + 1] = "wrong" end, { element = "other" })
    local raw = '{"type":"click","window":' .. w.id .. ',"element":"caption","path":["caption","button"]}'
    eq(app:_on_native_event(raw), 0)
    eq(table.concat(seen, ","), "caption")
    app:close()
end)

test("close_requested veto and subscription removal during dispatch", function()
    local app = headless()
    local w = app:open("<p>w</p>")
    w:on("close_requested", function() return false end)
    eq(app:_on_native_event('{"type":"close_requested","window":' .. w.id .. '}'), 1)
    local seen = {}
    local later
    app:on("started", function() later:close() end)
    later = app:on("started", function() seen[#seen + 1] = "removed" end)
    app:on("started", function() seen[#seen + 1] = "kept"; app:stop() end)
    app:run()
    eq(table.concat(seen, ","), "kept")
    app:close()
end)

test("unsubscribe stops delivery and is idempotent", function()
    local app = headless()
    local n = 0
    local sub = app:on("timer", function() n = n + 1 end)
    app:timer(1, function() end)
    app:timer(30, function() app:stop() end)
    sub:close(); sub:close()
    app:run()
    eq(n, 0)
    app:close()
end)

test("timers: one-shot, repeat with cancel, cancelled never fires", function()
    local app = headless()
    local order, ticks, cancelled_fired = {}, 0, false
    local rep
    rep = app:timer(5, function() ticks = ticks + 1; if ticks == 3 then rep:cancel() end end, { ["repeat"] = true })
    local never = app:timer(10, function() cancelled_fired = true end)
    never:cancel()
    app:timer(2, function(e) order[#order + 1] = "once"; eq(e.type, "timer") end)
    app:timer(150, function() app:stop() end)
    app:run()
    eq(ticks, 3); eq(cancelled_fired, false); eq(order[1], "once"); eq(#order, 1)
    app:close()
end)

test("post: order, nesting, results, failures and cancellation", function()
    local app = headless()
    local order = {}
    local f1 = app:post(function() order[#order + 1] = 1; return "one" end)
    local f2 = app:post(function() order[#order + 1] = 2; app:post(function() order[#order + 1] = 4 end) end)
    local f3 = app:post(function() order[#order + 1] = 3; error("posted failure") end)
    local f4 = app:post(function() order[#order + 1] = "never" end)
    truthy(f4:cancel(), "cancel before run")
    raises(function() f1:result() end, "not run")
    app:post(function() app:post(function() app:stop() end) end)
    app:run()
    eq(table.concat(order, ","), "1,2,3,4")
    eq(f1:result(), "one"); truthy(f1:done())
    truthy(f2:done()); truthy(f3:done())
    raises(function() f3:result() end, "posted failure")
    truthy(f4:cancelled()); raises(function() f4:result() end, "cancelled")
    eq(f1:cancel(), false)
    raises(function() app:post(function() end) end, "no longer accepting")
    app:close()
end)

test("post: many in order, bounded queue is an error not a crash", function()
    local app = headless()
    local last, bad = 0, false
    for i = 1, 400 do app:post(function() if i ~= last + 1 then bad = true end last = i end) end
    app:post(function() app:stop() end)
    app:run()
    eq(last, 400); eq(bad, false)
    app:close()
    local app2 = headless()
    local err
    for _ = 1, 700 do
        local ok, e = pcall(app2.post, app2, function() end)
        if not ok then err = e; break end
    end
    truthy(err and ui4me.is_error(err) and err.code == 5, "queue full is resource_limit")
    app2:close()
end)

test("pending posts are cancelled on close and stop", function()
    local app = headless()
    local f = app:post(function() end)
    app:close()
    truthy(f:cancelled()); app:close()
    local app2 = headless()
    local g = app2:post(function() end)
    app2:stop()
    app2:run()
    truthy(g:done() or g:cancelled())
    app2:close()
end)

test("handler errors are captured, stop the loop and surface from run", function()
    local app = headless()
    local after = false
    app:on("started", function() error("boom in handler") end)
    app:on("stopped", function() after = true end)
    local err = raises(function() app:run() end, "boom in handler")
    truthy(tostring(err):find("stack traceback"), "traceback kept")
    truthy(after, "native stopped event still delivered")
    app:close()
    local again = headless()
    run_started(again)
    again:close()
    -- A table error value and a timer error survive intact.
    local app3 = headless()
    local sentinel = { tag = "mine" }
    app3:timer(1, function() error(sentinel, 0) end)
    local got = raises(function() app3:run() end)
    eq(got, sentinel)
    app3:close()
    -- Only the first error is kept.
    local app4 = headless()
    app4:on("started", function() error("first") end)
    app4:on("started", function() error("second") end)
    local e4 = raises(function() app4:run() end, "first")
    truthy(not tostring(e4):find("second"))
    app4:close()
end)

test("no callback after close; handler tables released", function()
    local app = headless()
    local n = 0
    app:on("started", function() n = n + 1; app:stop() end)
    app:run()
    eq(n, 1)
    app:close()
    eq(app._cb, nil, "native callback freed")
    eq(app._nhandlers, 0)
    raises(function() app:on("started", function() end) end, "terminal")
    raises(function() app:timer(1, function() end) end, "terminal")
    eq(app:_on_native_event('{"type":"started"}'), 0) -- a late event finds no handlers
    eq(n, 1)
end)

test("a native thread can stop the loop (thread-safe ABI call)", function()
    -- The start routine is the C function ui4me_session_stop itself (one argument, the
    -- session id passed as the thread argument): no Lua code runs on the second thread.
    local lib = ffi.load(ui4me.build_info().library_path)
    local app = headless()
    local win = ffi.os == "Windows"
    local handle
    if win then
        ffi.cdef [[
        void *CreateThread(void *attrs, size_t stack, uint32_t (*fn)(void *), void *arg, uint32_t flags, uint32_t *id);
        uint32_t WaitForSingleObject(void *h, uint32_t ms);
        int CloseHandle(void *h);
        ]]
    else
        ffi.cdef [[
        int pthread_create(unsigned long *thread, const void *attr, void *(*fn)(void *), void *arg);
        int pthread_join(unsigned long thread, void **ret);
        ]]
    end
    local tid = ffi.new("unsigned long[1]")
    local stopped = false
    app:on("stopped", function() stopped = true end)
    app:timer(20, function()
        -- Spawned from the owner thread while run() is blocking in native code.
        local arg = ffi.cast("void *", app._session)
        if win then
            handle = ffi.C.CreateThread(nil, 0, ffi.cast("uint32_t (*)(void *)", lib.ui4me_session_stop), arg, 0, nil)
            assert(handle ~= nil)
        else
            local rc = ffi.C.pthread_create(tid, nil, ffi.cast("void *(*)(void *)", lib.ui4me_session_stop), arg)
            assert(rc == 0, "pthread_create " .. rc)
        end
    end)
    app:timer(10000, function() error("native-thread stop never arrived") end)
    app:run()
    if win then ffi.C.WaitForSingleObject(handle, 5000); ffi.C.CloseHandle(handle)
    else ffi.C.pthread_join(tid[0], nil) end
    truthy(stopped, "stopped event")
    app:close()
end)

print(string.format("\n%d passed, %d failed", passed, failed))
if failed > 0 then print("failed: " .. table.concat(names, ", ")) os.exit(1) end
os.exit(0)
