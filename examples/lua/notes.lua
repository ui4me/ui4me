-- A small multi-control notes app written for the LuaJIT binding: input + Add button + list +
-- Clear button + counter. Uses only the public `ui4me` module.
--
--   export UI4ME_NATIVE_LIB=/absolute/path/to/libui4me_core.so      (ui4me_core.dll on Windows)
--   build/luajit/src/luajit examples/lua/notes.lua [--headless] [--seconds N] [--state FILE]
--
-- Type a note and press Enter or click Add; click a note to toggle it done; Clear removes all.
-- `--state FILE` rewrites a small JSON file after each change (for automated journeys).
-- The probe tests/native/lua_probe.lua loads this file as a module (UI4ME_NOTES_MODULE = true).
local here = (debug.getinfo(1, "S").source:sub(2):match("^(.*)[/\\][^/\\]*$")) or "."
package.path = here .. "/../../bindings/lua/?.lua;" .. package.path
local ui4me = require("ui4me")

local HTML = [[
<style>
body { font: 16px sans-serif; margin: 16px; }
#row { display: flex; gap: 8px; }
#new { flex: 1; padding: 6px; }
button { padding: 6px 14px; }
ul { padding-left: 24px; }
li { padding: 2px 0; }
li.done { color: #888; text-decoration: line-through; }
#count { color: #555; }
</style>
<h1>Notes</h1>
<div id="row"><input id="new" placeholder="New note"><button id="add">Add</button><button id="clear">Clear</button></div>
<ul id="list"></ul>
<p id="count">0 notes</p>
]]

local function escape_html(s)
    return (s:gsub("[&<>\"']", { ["&"] = "&amp;", ["<"] = "&lt;", [">"] = "&gt;", ['"'] = "&quot;", ["'"] = "&#39;" }))
end

local notes = {}

--- Wire the UI onto `app`. Returns a state table {window, items, errors, added, toggled, cleared}.
function notes.setup(app, opts)
    opts = opts or {}
    local win = app:open(HTML, { title = "UI4ME Lua notes", width = opts.width or 520, height = opts.height or 420 })
    local state = { window = win, items = {}, next_id = 1, added = 0, toggled = 0, cleared = 0, errors = {} }

    local function refresh_count()
        local n = #state.items
        win:set_text("count", n == 1 and "1 note" or (n .. " notes"))
    end

    local function save()
        if not opts.state_file then return end
        local items = {}
        for i, item in ipairs(state.items) do items[i] = { id = item.id, text = item.text, done = item.done } end
        local f = io.open(opts.state_file, "wb")
        if f then
            f:write(ui4me.json.encode({ items = ui4me.json.array(items), added = state.added, toggled = state.toggled,
                cleared = state.cleared, input = win:get_value("new"), count = win:get_text("count") }))
            f:close()
        end
    end

    local function add()
        local text = win:get_value("new"):match("^%s*(.-)%s*$")
        if text == "" then return end
        local id = "n" .. state.next_id
        state.next_id = state.next_id + 1
        state.items[#state.items + 1] = { id = id, text = text, done = false }
        win:append_html("list", '<li id="' .. id .. '">' .. escape_html(text) .. "</li>")
        win:set_value("new", "")
        win:focus("new")
        state.added = state.added + 1
        refresh_count()
        save()
    end

    win:on("click", add, { element = "add" })
    win:on("keydown", function(e) if e.key == "Enter" then add() end end, { element = "new" })
    win:on("click", function(e)
        -- Clicks inside the list arrive with the clicked <li> as `element`.
        for _, item in ipairs(state.items) do
            if item.id == e.element then
                item.done = not item.done
                if item.done then win:add_class(item.id, "done") else win:remove_class(item.id, "done") end
                state.toggled = state.toggled + 1
                save()
                return
            end
        end
    end, { element = "list" })
    win:on("click", function()
        win:set_html("list", "")
        state.items = {}
        state.cleared = state.cleared + 1
        refresh_count()
        save()
    end, { element = "clear" })
    win:on("closed", function() app:stop() end)
    win:focus("new")
    save()
    return state
end

local function main(argv)
    local backend, seconds, state_file = "native", nil, nil
    local i = 1
    while i <= #argv do
        local a = argv[i]
        if a == "--headless" then backend = "headless"
        elseif a == "--seconds" then i = i + 1; seconds = tonumber(argv[i])
        elseif a == "--state" then i = i + 1; state_file = argv[i]
        else io.stderr:write("unknown argument " .. a .. "\n"); return 2 end
        i = i + 1
    end
    local app = ui4me.App { backend = backend, app_id = "org.ui4me.luanotes" }
    notes.setup(app, { state_file = state_file })
    if seconds then app:timer(math.floor(seconds * 1000), function() app:stop() end) end
    local ok, err = pcall(app.run, app)
    app:close()
    if not ok then io.stderr:write(tostring(err) .. "\n"); return 1 end
    return 0
end

if UI4ME_NOTES_MODULE then return notes end
os.exit(main(arg or {}))
