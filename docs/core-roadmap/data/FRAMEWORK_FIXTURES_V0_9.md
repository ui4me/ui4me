# Framework-style fixtures (Core 0.9, F0910)

Source: `crates/ui4me-renderer/src/document/framework_fixtures_tests.rs`. The fixtures are
hand-written markup and CSS in the style of three common frameworks. No framework files are
vendored, no script runs, and there is no web loader. Each fixture is rendered at 375, 768 and
1280 CSS px, and its geometry is asserted. Any `UNSUPPORTED_FEATURE` diagnostic fails the test
unless the feature is in the exception list below.

| Fixture | Patterns covered | Checked |
| --- | --- | --- |
| Bootstrap-style | `:root` custom-property theme, `calc(var())` gutters, a container with `max-width` per breakpoint, a flex navbar whose nav is a column below `lg` and a row from `lg`, a 12-column flex `.row` (`col-md-4`/`col-md-8`), `.form-control`, `.table`, `d-none d-md-block` (`!important` order), a component colour override by a more specific rule | container widths 375/720/1140; stacked versus side-by-side columns; the 1/3 split; nav direction; control and table widths; override colour |
| Tailwind-style (v3 output) | utility classes, escaped `sm:`/`md:`/`lg:` breakpoint classes, `grid-cols-*` with `minmax(0,1fr)`, `gap`, `hidden md:block`, `shrink-0`, `truncate`, `rgb(… / var(--tw-bg-opacity))`, shadows | 1/2/4 grid columns; sidebar hidden below `md` and 256 px from `md`; content beside the sidebar; one-line truncation; full-width header |
| Tailwind-style (v4 output) | `@layer` order declared up front, `@property`, `oklch()` theme variables, `color-mix(in oklab, …)` | later layers win over earlier ones regardless of source order; modern colours compute |
| Mantine-style app shell | CSS variables, `prefers-color-scheme` theme switch, a fixed header and navbar, `@media (max-width: 48em)`, a flex `group` with `gap`, `min-height: 100vh`, `box-shadow` | the fixed regions keep their place under page scroll; navbar hidden on small screens; flex gap; the dark scheme switches the theme |

## Documented exceptions

None of the fixtures reports an unsupported feature, so the `EXCEPTIONS` list in the test is
empty. These are out of scope by design:

- **Components that need a framework's JavaScript.** Dropdowns, collapse, modals, tooltips,
  carousels, Mantine hooks and the like. The app implements the behaviour through the Core API:
  native `dialog`, `popover`, `details`, and DOM writes from Python or PowerShell.
- **Tailwind's build step.** Tailwind's JIT, `@apply`, `@tailwind`, `@theme` and `@config`
  resolve when the stylesheet is built, not in the engine. Ship the built CSS.
- **Hover-only menus that rely on `:hover` reaching through scripts.** Plain `:hover` and
  `:focus-within` work.
- **Remote resources.** Web fonts, CDN stylesheets and `url()` images over the network follow
  the Core resource policy (packaged or local files).
