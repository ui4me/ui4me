# Developer diagnostics schema 1 (F1008)

Public commands `get_diagnostics` and `explain` (Core 0.10). Both are window commands, owner thread only, and
never expose engine pointers, arena indices or node handles. The older `diagnostics` command keeps its
original, unversioned shape.

## `get_diagnostics`

Request: `{"op":"get_diagnostics","window":W, "redact":true, "since":N, "kinds":["css_unsupported", ...]}`

* `redact` (default `true`): absolute file paths and `file:` URLs become `<path>`, `http(s)` URLs lose their query
  and fragment, `data:` URLs become `data:<redacted>`, long quoted text is replaced by `<text>`. Applies to `message`
  and `element`. `false` returns the text verbatim.
* `since` (default none): return only items whose `seq` is greater than the cursor. Use the highest `seq` already seen.
* `kinds` (default all): filter by kind. An unknown kind is an `invalid argument` error.

Response (exact top-level keys):

```json
{"schema": 1, "items": [ ... ], "dropped": 0}
```

Item keys: `seq`, `kind`, `code`, `stage`, `message`, `count` always; `feature` and `element` when applicable.

| key | meaning |
| --- | --- |
| `seq` | Monotonic per window, assigned when a distinct report is first observed. Stable for the life of the report. |
| `kind` | `css_unsupported`, `stale_reference`, `layout`, `paint`, `resource`, `text`, `command` (closed set for schema 1). |
| `code` | Stable engine code name (`UNSUPPORTED_FEATURE`, `STALE_HANDLE`, `FILE_NOT_FOUND`, ...) or one of the core names `INVALID_ARGUMENT`, `INVALID_STATE`, `WRONG_THREAD`, `LIMIT`, `NATIVE`, `CALLBACK_FAILED`, `IO`, plus `UNKNOWN_ELEMENT` for a command that named an element id that does not exist. |
| `stage` | Pipeline stage (`parse`, `cascade`, `box`, `text`, `layout`, `scene`, `raster`, `resource`, `host`, ...) or `command`. |
| `feature` | Profile feature id (for example `css.property.view-transition`) for unsupported-CSS reports. |
| `element` | The element id a failed command named. |
| `message` | Short human-readable text, at most 256 characters. |
| `count` | How often the same report was seen (commands increment; engine reports count once). |

Behaviour:

* The view is a log of distinct reports. Engine reports are snapshotted from the current document at call time (the
  call brings style and layout up to date first); failed window commands are logged when they fail. Repeating the same
  report increases `count` and keeps `seq`.
* Bounded: the log keeps 256 reports per window; the oldest are evicted and counted in `dropped`. One call returns at
  most 128 items; page with `since`.
* Adding new item keys, kinds or codes is not a schema break for readers that ignore unknown keys; the key set above
  is what schema 1 guarantees.

## `explain`

Request: `{"op":"explain","window":W,"element":"id-or-node:ref","property":"width","redact":true}`

Answer for a property (exact keys: `schema`, `property`, `element`, `status`, `reason`; `value` when computed;
`feature` when `unsupported`):

| `status` | meaning |
| --- | --- |
| `applied` | The declaration takes effect; `value` is the computed value. |
| `unsupported` | The CSS profile excludes the property (`feature` names the row). It is parsed and ignored. |
| `not_applicable` | The property exists but does not apply: `display: none` on the element or an ancestor, `content-visibility: hidden` on an ancestor, `display: inline` for width/height/vertical margins, `display: contents`, offsets on `position: static`, flex properties outside flex/grid. |
| `overridden` | The element's inline `style` declared a keyword that the cascade or an adjustment replaced with a different keyword (`value` is the computed result). Declarations lost to selector specificity in author sheets are not detected. |
| `unknown_property` | The name is not a CSS property the engine knows. |

Without `property`, the answer is `{schema, status: "applied"|"not_applicable", element, reason, properties: [...]}`
where `properties` explains each property declared in the element's inline `style` (at most 16).

An unknown, removed or out-of-date element or `node:` reference does not raise an error. The answer is
`{"schema":1,"status":"stale_reference","element":...,"reason":...,"property"?:...}`.

`redact` (default `true`) applies the same text redaction to `reason` and `value`.

## Bindings

* Python: `Window.get_diagnostics(redact=True, since=None, kinds=None)`, `Window.explain(element, property=None)`.
* PowerShell: `$window.GetDiagnosticsJson($redact, $since, $kinds)`, `$window.ExplainJson($element, $property, $redact)`.
