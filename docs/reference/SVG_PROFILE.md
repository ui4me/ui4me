# SVG static presentation profile

Fixed profile of what UI4ME Core draws for static SVG. It covers two entry points that share one
rasteriser (usvg 0.49 parse + resvg/tiny-skia render, no `text` feature, no system fonts):

* **External SVG** (`<img src=*.svg>`, CSS `url(*.svg)`): `crates/ui4me-assets/src/svg*`. Unchanged by
  0.9.
* **Inline `<svg>`** in HTML: `crates/ui4me-renderer/src/pipeline/inline_svg.rs`. The subtree
  is serialised into a standalone document (profile elements only, CSS resolved, references limited
  to the same document) and goes through the external path as a `data:image/svg+xml` image; the
  `<svg>` is a replaced box (CSS `width`/`height`, the `width`/`height` attributes, `viewBox` ratio,
  300 x 150 default). Caches are keyed by the serialised content and the device size.

Conformance corpus: `crates/ui4me-renderer/src/document/svg_tests.rs` (`CORPUS`, pixel samples, not
goldens). A feature outside this profile is dropped, never approximated, and reported as an
`UNSUPPORTED_FEATURE` under the key shown in the last column.

## Supported (drawn)

| Area | Elements / attributes |
|---|---|
| Structure | `svg` (nested allowed), `g`, `defs`, `symbol`, `use` (same-document `#id` only), `switch`, `a` (drawn as a group, no navigation), `title`/`desc` (not drawn; `title` names an inline `<svg>`) |
| Shapes | `path`, `rect` (`rx`/`ry`), `circle`, `ellipse`, `line`, `polyline`, `polygon` |
| Geometry | `viewBox`, `preserveAspectRatio` (all alignments, `meet`/`slice`/`none`), `transform` list (`matrix translate scale rotate skewX skewY`), user-space and bounding-box units |
| Paint | `fill`, `stroke`, `*-opacity`, `opacity`, `fill-rule`, `clip-rule`, `stroke-width/linecap/linejoin/miterlimit/dasharray/dashoffset`, `paint-order`, `color` + `currentColor`, `display`, `visibility`, `shape-rendering` |
| Gradients | `linearGradient`, `radialGradient` (`fx/fy/fr`), `stop`, `spreadMethod`, `gradientTransform`, `href` inheritance between gradients |
| Patterns | `pattern` (units, `viewBox`, `patternTransform`) |
| Clipping / masking | `clipPath` (units, nested `clip-path`), `mask` (luminance and alpha, `maskUnits`/`maskContentUnits`) |
| Markers | `marker` with `marker-start/mid/end`, `markerUnits`, `orient`, `refX/refY`, `viewBox` |
| Filters | `filter` with `feBlend feColorMatrix feComponentTransfer(feFunc*) feComposite feConvolveMatrix feDiffuseLighting feDisplacementMap feDropShadow feFlood feGaussianBlur feImage feMerge feMorphology feOffset feSpecularLighting feTile feTurbulence`, `filterUnits`/`primitiveUnits`, `in`/`result`, `color-interpolation-filters` |
| Images | `image` with a `data:` URL (PNG/JPEG/GIF/WebP/nested SVG, nested depth and pixel budget per the external-SVG policy) |
| Inline CSS hooks | author rules of the document's `<style>` elements, matched with the engine's selector matcher and ordered by specificity, for: `fill fill-opacity fill-rule stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset clip-rule color pointer-events marker-* shape-rendering stop-color stop-opacity flood-color flood-opacity opacity display visibility transform clip-path mask filter`; the element's `style` attribute (wins over rules, rules win over presentation attributes); `var(--x[, fallback])` resolved from the `<svg>`'s computed custom properties; inherited ones also flow from HTML ancestors (`.btn { fill: currentColor }`); `color` is the computed `color` of the `<svg>` (so `currentColor` follows CSS inheritance, themes and `prefers-color-scheme`) |
| HTML-side box | the inline `<svg>` box takes `display`, sizing, margins, `opacity`, `transform`, `filter`, `clip-path`, `overflow`, `object-fit`/`object-position` like any replaced element |
| DOM | `set_attribute`, `set_text`, `insert_html`, `replace_children_html` anywhere under the `<svg>` re-render it; `id`s on shapes/groups are click targets |
| Hit testing | topmost shape whose fill area (default: when filled) or stroke band (when stroked) contains the point, in viewBox/transform space (usvg-flattened outlines, curves at 12 steps); `pointer-events` `none / all / visible* / painted / fill / stroke` on shapes and groups (inherited); `pointer-events: none` on the `<svg>` passes the pointer through to what is behind; otherwise the `<svg>` itself is the target. Events report the shape as `element` and its ancestors in `path` |
| Accessibility | an inline `<svg>` with `role=img`/`image`, `aria-label` or a `<title>` child is an Image named by the label or title; `aria-hidden` and unlabelled decorative `<svg>` are not exposed |

## Unsupported (dropped, reported)

| Feature | Behaviour | Report key |
|---|---|---|
| `<text>`, `tspan`, `textPath` | not drawn (the rasteriser has no text feature or font database); the rest of the picture is drawn | `svg.text` |
| `<foreignObject>` | dropped with its subtree | `svg.foreignobject` |
| SMIL / animation elements (`animate`, `animateTransform`, `animateMotion`, `set`, `discard`) | dropped; the static value applies | `svg.animation` |
| `<script>`, `on*` attributes | the whole document is refused at parse (same rule as HTML) | none (parse error) |
| `href` / `xlink:href` to another file or a URL (`use`, `image`, `feImage`, fonts, `<a>`), `url()` to anything but `#fragment` | attribute or declaration dropped; remote `image` is blocked and never fetched | `svg.external-reference` |
| `<style>` inside the SVG as a stylesheet of its own | its rules are part of the document's author rules (same as any `<style>`); `@media`, `@supports`, `@font-face` and other at-rules in them are not applied to SVG content | none |
| CSS `!important`, `:hover`/`:focus` state restyling of shapes | `!important` is treated as normal; state selectors match at the time of the scene build only | none |
| CSS properties not listed above on shapes (`transform-origin`, `transform-box`, `vector-effect`, `mix-blend-mode`, `font-*` for text, `paint-order` via CSS) | ignored; use the presentation attribute | none |
| SVG fonts, `<cursor>`, `<view>`, `<metadata>`, scripting DOM (`getBBox`, `SVGElement` API) | not provided | none |
| Gzip (`.svgz`) | refused | resource error |
| A nested `<svg>` is part of its outermost `<svg>`; it is not a separate box and cannot be an `<img>` target | | none |

## Limits and fallback

| Limit | Value | Over the limit |
|---|---|---|
| Elements serialised per inline `<svg>` | 2,000 | element renders nothing, `svg.inline.rejected` |
| Element depth | 48 | same |
| One attribute value (path data, point lists) | 64 KiB | same |
| Serialised document | 512 KiB | same |
| Author rules considered | 4,000 | later rules ignored |
| Hit table | 5,000 shapes, 200,000 outline points | the `<svg>` element is hit as a whole |
| Raster size / budgets | external-SVG policy: 65,535 px per side, decoded-memory budget, 4 MiB data payload, 1,000,000-element document limit | picture fails with the resource error (`SIZE_LIMIT`, `BUDGET_EXCEEDED`) and `svg.inline.rejected` |
| Malformed content | well-formed by construction (serialised from the DOM); invalid path data, zero-size `viewBox` and unknown elements draw nothing for that part | never a panic |
| Rasterisation | re-done when content, size or device scale changes; the previous picture stays on screen while the new one is made | |

Known approximations: hit outlines of strokes use round joins/caps; `use` instances report the instancing
element's descendants under the referenced element's id.
