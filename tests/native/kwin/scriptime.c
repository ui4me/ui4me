/* Dev/test tool: a scripted Wayland input method for a (virtual) KWin (zwp_input_method_v1).
 *
 * KWin starts it with `kwin_wayland --inputmethod <this binary>` and hands it a private
 * WAYLAND_SOCKET. KWin bridges it to the application's text-input-v3 (winit), so preedit and commit
 * strings travel the same compositor path as a real IME such as fcitx5 or ibus, with exactly the
 * text a test chooses. Commands are read line by line from the FIFO named by $UI4ME_IME_CMD; one
 * reply line per command is written to the FIFO $UI4ME_IME_REPLY:
 *
 *   active                  -> "active N" (N = activations so far) or "inactive N"
 *   preedit CURSOR TEXT     -> preedit TEXT, cursor at byte CURSOR; on reset KWin commits TEXT
 *   preedit_nocommit C TEXT -> the same, but nothing is committed on reset
 *   commit TEXT             -> commit TEXT (ends the composition)
 *   clear                   -> empty preedit (cancel)
 *   events                  -> "events a,d,r,..." activate/deactivate/reset/surrounding since last call
 *
 * TEXT is the rest of the line (UTF-8). Not shipped. */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <wayland-client.h>
#include "input-method-client-protocol.h"

static struct zwp_input_method_v1 *im;
static struct zwp_input_method_context_v1 *ctx;
static uint32_t serial;
static int activations;
static char events[4096];

static void note(const char *what) {
  size_t n = strlen(events);
  if (n + strlen(what) + 2 < sizeof events) {
    if (n) strcat(events, ",");
    strcat(events, what);
  }
}
static void c_surrounding(void *d, struct zwp_input_method_context_v1 *c, const char *text, uint32_t cursor, uint32_t anchor) {
  char buf[600];
  snprintf(buf, sizeof buf, "surrounding:%u:%u:%.500s", cursor, anchor, text);
  for (char *p = buf; *p; p++) if (*p == ',' || *p == '\n') *p = ' ';
  note(buf);
}
static void c_reset(void *d, struct zwp_input_method_context_v1 *c) { note("reset"); }
static void c_content_type(void *d, struct zwp_input_method_context_v1 *c, uint32_t hint, uint32_t purpose) {
  char buf[64];
  snprintf(buf, sizeof buf, "content:%u:%u", hint, purpose);
  note(buf);
}
static void c_invoke(void *d, struct zwp_input_method_context_v1 *c, uint32_t button, uint32_t index) {}
static void c_commit_state(void *d, struct zwp_input_method_context_v1 *c, uint32_t s) { serial = s; }
static void c_language(void *d, struct zwp_input_method_context_v1 *c, const char *l) {}
static const struct zwp_input_method_context_v1_listener cl = {c_surrounding, c_reset, c_content_type, c_invoke, c_commit_state, c_language};

static void activate(void *d, struct zwp_input_method_v1 *m, struct zwp_input_method_context_v1 *c) {
  if (ctx) zwp_input_method_context_v1_destroy(ctx);
  ctx = c;
  serial = 0;
  activations++;
  zwp_input_method_context_v1_add_listener(ctx, &cl, NULL);
  note("activate");
}
static void deactivate(void *d, struct zwp_input_method_v1 *m, struct zwp_input_method_context_v1 *c) {
  if (c == ctx) ctx = NULL;
  zwp_input_method_context_v1_destroy(c);
  note("deactivate");
}
static const struct zwp_input_method_v1_listener ml = {activate, deactivate};

static void reg(void *d, struct wl_registry *r, uint32_t n, const char *i, uint32_t v) {
  if (!strcmp(i, "zwp_input_method_v1")) {
    im = wl_registry_bind(r, n, &zwp_input_method_v1_interface, 1);
    zwp_input_method_v1_add_listener(im, &ml, NULL);
  }
}
static void rem(void *d, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener rl = {reg, rem};

int main(void) {
  const char *cmd_path = getenv("UI4ME_IME_CMD"), *reply_path = getenv("UI4ME_IME_REPLY");
  if (!cmd_path || !reply_path) { fprintf(stderr, "scriptime: UI4ME_IME_CMD/REPLY unset\n"); return 2; }
  struct wl_display *dpy = wl_display_connect(NULL);
  if (!dpy) { fprintf(stderr, "scriptime: no wayland display\n"); return 3; }
  struct wl_registry *r = wl_display_get_registry(dpy);
  wl_registry_add_listener(r, &rl, NULL);
  wl_display_roundtrip(dpy);
  if (!im) { fprintf(stderr, "scriptime: compositor offers no zwp_input_method_v1\n"); return 4; }
  int cmd = open(cmd_path, O_RDWR | O_NONBLOCK); /* RDWR: never sees EOF when a writer goes away */
  int reply = open(reply_path, O_RDWR);
  if (cmd < 0 || reply < 0) { perror("scriptime: fifo"); return 5; }
  char line[8192];
  size_t used = 0;
  for (;;) {
    wl_display_flush(dpy);
    struct pollfd p[2] = {{wl_display_get_fd(dpy), POLLIN, 0}, {cmd, POLLIN, 0}};
    if (poll(p, 2, -1) < 0 && errno != EINTR) return 6;
    if (p[0].revents & POLLIN) {
      if (wl_display_dispatch(dpy) < 0) return 0; /* compositor gone */
    }
    if (p[0].revents & (POLLERR | POLLHUP)) return 0;
    if (!(p[1].revents & POLLIN)) continue;
    ssize_t got = read(cmd, line + used, sizeof line - 1 - used);
    if (got <= 0) continue;
    used += (size_t)got;
    char *nl;
    while ((nl = memchr(line, '\n', used))) {
      *nl = 0;
      char out[4200] = "ok";
      wl_display_roundtrip(dpy); /* current serial and activation state */
      if (!strncmp(line, "active", 6)) {
        snprintf(out, sizeof out, "%s %d", ctx ? "active" : "inactive", activations);
      } else if (!strncmp(line, "events", 6)) {
        snprintf(out, sizeof out, "events %s", events);
        events[0] = 0;
      } else if (!ctx) {
        strcpy(out, "error inactive");
      } else if (!strncmp(line, "preedit ", 8) || !strncmp(line, "preedit_nocommit ", 17)) {
        int keep = line[7] == ' ';
        char *rest = line + (keep ? 8 : 17);
        int cursor = atoi(rest);
        char *text = strchr(rest, ' ');
        text = text ? text + 1 : "";
        zwp_input_method_context_v1_preedit_cursor(ctx, cursor);
        zwp_input_method_context_v1_preedit_string(ctx, serial, text, keep ? text : "");
      } else if (!strncmp(line, "commit ", 7)) {
        zwp_input_method_context_v1_commit_string(ctx, serial, line + 7);
      } else if (!strcmp(line, "clear")) {
        zwp_input_method_context_v1_preedit_cursor(ctx, 0);
        zwp_input_method_context_v1_preedit_string(ctx, serial, "", "");
      } else {
        strcpy(out, "error unknown command");
      }
      wl_display_roundtrip(dpy);
      strcat(out, "\n");
      if (write(reply, out, strlen(out)) < 0) return 7;
      used -= (size_t)(nl + 1 - line);
      memmove(line, nl + 1, used);
    }
  }
}
