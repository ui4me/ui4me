# Accessibility and keyboard contracts

Core provides native accessibility trees (AT-SPI on Linux and UI Automation on Windows) and control semantics; UI4ME adds accessible names, labels, keyboard navigation and component focus management. **Static ARIA markup does not prove accessible interaction.**

Rules: label each input; associate errors/help via `aria-describedby`; expose errors with `role=alert` and passive status with `role=status`; icon-only buttons need a nonempty accessible name; disabled controls must be both visually and functionally disabled; preserve input focus and text/IME composition during keyed updates.

Test each interactive component in an actual desktop session using keyboard Tab, Shift+Tab, arrows, Home/End, Enter, Space and Escape. Verify focus return when dialogs/menu close, focus first invalid form field, and screen-reader announcements where applicable. Wayland compositor restrictions mean focus requests can be refused; report capability rather than promising focus. Respect desktop high-contrast, reduced motion and large text where Core exposes them.

Automated render tests establish layout/DOM; fake event tests establish component logic; only native keyboard+AT journeys establish usable accessibility. Record unexecuted evidence separately.
