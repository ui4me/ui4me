-- Native desktop probe for the LuaJIT binding (F1203). Self-checking; runs on a real window
-- (the private virtual KWin on Linux). Automated compositor input, not a person.
--
--   python3 tests/native/kwin/chat_journey.py --plain --out DIR -- \
--       build/luajit/src/luajit tests/native/lua_probe.lua --out DIR/lua.json
--   (UI4ME_NATIVE_LIB must name libui4me_core.so / ui4me_core.dll)
--
-- It opens examples/lua/notes.lua on the native backend and, on the single Lua thread, drives it
-- with timers: keyboard input through KWin fake input (built by the Python harness helper),
-- then checks the events the app received, the DOM, errors, post/timer order and a clean close.
-- Cases whose input path is unavailable are reported "blocked", never "passed".
local here = (debug.getinfo(1, "S").source:sub(2):match("^(.*)[/\\][^/\\]*$")) or "."
local root = here .. "/../.."
package.path = root .. "/bindings/lua/?.lua;" .. package.path
local ui4me = require("ui4me")
local json = ui4me.json
io.stdout:setvbuf("no")

local out_file
do
    local i = 1
    while i <= #arg do
        if arg[i] == "--out" then i = i + 1; out_file = arg[i] end
        i = i + 1
    end
end
assert(out_file, "usage: lua_probe.lua --out FILE.json")
local out_dir = out_file:match("^(.*)[/\\][^/\\]*$") or "."

local cases = {}
local function check(id, ok, details, status)
    cases[#cases + 1] = { id = id, status = status or (ok and "passed" or "failed"), details = details }
    print(cases[#cases].status, id, json.encode(details):sub(1, 300))
end

-- Keyboard input via org_kde_kwin_fake_input (Linux only).
local fake
if ui4me.build_info().library_path and package.config:sub(1, 1) == "/" then
    local py = string.format(
        [[import sys; from pathlib import Path; sys.path.insert(0, %q); from chat_journey import build_fakeinput; print(build_fakeinput(Path(%q)))]],
        root .. "/tests/native/kwin", out_dir)
    local p = io.popen("python3 -I -c '" .. py:gsub("'", "'\\''") .. "' 2>/dev/null")
    local binary = p and p:read("*l")
    if p then p:close() end
    if binary and binary ~= "" then
        fake = io.popen(binary .. " serve", "w")
    end
end
local function send(line) fake:write(line .. "\n"); fake:flush() end

UI4ME_NOTES_MODULE = true
local notes = dofile(root .. "/examples/lua/notes.lua")

local app = ui4me.App { backend = "native", app_id = "org.ui4me.luaprobe" }
local state = notes.setup(app, { width = 520, height = 420 })
local win = state.window
local seen = { click = {}, keydown = 0 }
win:on("click", function(e) seen.click[#seen.click + 1] = e.element end)
win:on("keydown", function() seen.keydown = seen.keydown + 1 end)

local order = {}
local steps = {}
local function step(delay, fn) steps[#steps + 1] = { delay = delay, fn = fn } end
local function run_steps(i)
    local s = steps[i]
    if not s then
        app:post(function() win:close() end)
        return
    end
    app:timer(s.delay, function()
        local ok, err = pcall(s.fn)
        if not ok then check("STEP_" .. i, false, { error = tostring(err) }) end
        run_steps(i + 1)
    end)
end

local function items() return table.concat(win:query("#list > li"), ",") end

step(1500, function()
    local r = { win:get_rect("new"), win:get_rect("add"), win:get_rect("list") }
    check("L01_window_laid_out", r[1].width > 100 and r[2].width > 20 and r[1].height > 10, { new = r[1], add = r[2] })
end)

step(100, function()
    -- post/timer ordering inside the native loop
    app:post(function() order[#order + 1] = "post1" end)
    app:post(function() order[#order + 1] = "post2" end)
    app:timer(5, function() order[#order + 1] = "timer" end)
end)
step(200, function()
    check("L02_post_and_timer_order", table.concat(order, ",") == "post1,post2,timer", order)
end)

step(100, function()
    win:focus("new")
    if fake then send("type hello"); send("key 28") end
end)
step(900, function()
    if not fake then check("L03_keyboard_enter_adds_note", false, "fake input unavailable", "blocked") return end
    local ok = state.added == 1 and state.items[1].text == "hello" and items() == "n1" and win:get_value("new") == ""
        and win:get_text("count") == "1 note" and seen.keydown >= 6
    check("L03_keyboard_enter_adds_note", ok, { added = state.added, items = items(), keydowns = seen.keydown,
        count = win:get_text("count") })
end)

step(100, function()
    if not fake then return end
    win:focus("new"); send("type second")
end)
step(600, function()
    if not fake then return end
    win:focus("add"); send("key 57")
end)
step(900, function()
    if not fake then check("L04_keyboard_activates_button", false, "fake input unavailable", "blocked") return end
    local clicked = false
    for _, e in ipairs(seen.click) do if e == "add" then clicked = true end end
    check("L04_keyboard_activates_button", state.added == 2 and clicked and items() == "n1,n2",
        { added = state.added, items = items(), clicks = seen.click })
end)

step(100, function()
    -- Synthetic click on the list item (pointer coordinates are not known to this probe).
    local raw = '{"type":"click","window":' .. win.id .. ',"element":"n1","path":["n1","list"]}'
    app:_on_native_event(raw)
    check("L05_list_item_toggle", state.toggled == 1 and win:get_attribute("n1", "class") == "done",
        { via = "synthetic click event", toggled = state.toggled, class = win:get_attribute("n1", "class") })
end)

step(100, function()
    local ok, err = pcall(win.get_text, win, "no-such-element")
    check("L06_unknown_element_error", not ok and ui4me.is_error(err) and err.code >= 1, { code = type(err) == "table" and err.code, message = type(err) == "table" and err.message })
end)

step(100, function()
    if fake then win:focus("clear"); send("key 57") else app:_on_native_event('{"type":"click","window":' .. win.id .. ',"element":"clear","path":["clear"]}') end
end)
step(900, function()
    check("L07_clear_empties_list", state.cleared == 1 and items() == "" and win:get_text("count") == "0 notes",
        { cleared = state.cleared, items = items(), via = fake and "keyboard" or "synthetic" })
end)

local closed_seen = false
win:on("closed", function() closed_seen = true end)
step(100, function() end)

local started = os.clock()
app:timer(120000, function() error("probe watchdog") end)
app:on("started", function() run_steps(1) end)
local ran, err = pcall(app.run, app)
check("L08_close_ends_run_cleanly", ran and closed_seen and win.closed, { error = (not ran) and tostring(err) or nil, closed = closed_seen })
local after_ok, after_err = pcall(win.get_text, win, "count")
check("L09_stale_window_rejected", not after_ok and tostring(after_err):find("closed") ~= nil, { error = tostring(after_err) })
app:close()
if fake then fake:close() end

local failed, blocked = 0, 0
for _, c in ipairs(cases) do
    if c.status == "failed" then failed = failed + 1 elseif c.status == "blocked" then blocked = blocked + 1 end
end
local result = { schema = 1, kind = "lua-binding-native-probe",
    status = failed > 0 and "failed" or (blocked > 0 and "blocked" or "passed"),
    environment = fake and "native backend, KWin fake input (automated, not a person)" or "native backend, no fake input",
    cases = cases }
local f = assert(io.open(out_file, "wb"))
f:write(json.encode(result))
f:close()
os.exit(failed == 0 and blocked == 0 and 0 or 1)
