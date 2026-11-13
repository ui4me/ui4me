/* Dev/test tool: drive a (virtual) KWin through org_kde_kwin_fake_input.
 * usage: fakeinput <cmd>...   |  fakeinput serve   (one command line per stdin line, 'ok' printed after each; keeps ONE
 *        fake-input device for the whole session, which avoids the seat's pointer capability flapping on every call)
 * cmds: move X Y | click [X Y] | down | up | key CODE | kd CODE | ku CODE | wheel V | type TEXT | sleep MS | tdown ID X Y | tmove ID X Y | tup ID
 * Needs KWIN_WAYLAND_NO_PERMISSION_CHECKS=1 in the compositor environment. Not shipped. Ported from the 0.1 alpha tooling. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <wayland-client.h>
#include "fake-input-client-protocol.h"
static struct org_kde_kwin_fake_input *fi;
static void reg(void *d, struct wl_registry *r, uint32_t n, const char *i, uint32_t v) {
  if (!strcmp(i, "org_kde_kwin_fake_input")) fi = wl_registry_bind(r, n, &org_kde_kwin_fake_input_interface, v < 5 ? v : 5);
}
static void rem(void *d, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener rl = {reg, rem};
static struct wl_display *dpy;
static void flush(void) {
  if (wl_display_roundtrip(dpy) < 0) {
    fprintf(stderr, "wayland roundtrip failed\n");
    exit(4);
  }
}
static void move(double x, double y) { org_kde_kwin_fake_input_pointer_motion_absolute(fi, wl_fixed_from_double(x), wl_fixed_from_double(y)); flush(); }
static void btn(int s) { org_kde_kwin_fake_input_button(fi, 0x110, s); flush(); }
static void key(int c) { org_kde_kwin_fake_input_keyboard_key(fi, c, 1); flush(); usleep(8000); org_kde_kwin_fake_input_keyboard_key(fi, c, 0); flush(); usleep(8000); }
/* US layout evdev codes for ascii subset */
static int code(char c, int *shift) {
  static const char *row1 = "qwertyuiop", *row2 = "asdfghjkl", *row3 = "zxcvbnm";
  *shift = 0;
  if (c >= 'A' && c <= 'Z') { *shift = 1; c += 32; }
  for (int i = 0; row1[i]; i++) if (row1[i] == c) return 16 + i;
  for (int i = 0; row2[i]; i++) if (row2[i] == c) return 30 + i;
  for (int i = 0; row3[i]; i++) if (row3[i] == c) return 44 + i;
  if (c >= '1' && c <= '9') return 2 + (c - '1');
  if (c == '0') return 11;
  if (c == ' ') return 57;
  if (c == '@') { *shift = 1; return 3; }
  if (c == '_') { *shift = 1; return 12; }
  if (c == ',') return 51;
  if (c == '/') return 53;
  if (c == '-') return 12;
  if (c == '.') return 52;
  return 0;
}
static void run(int argc, char **argv) {
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "move")) { move(atof(argv[i+1]), atof(argv[i+2])); i += 2; }
    else if (!strcmp(argv[i], "click")) {
      if (i + 2 < argc && argv[i+1][0] >= '0' && argv[i+1][0] <= '9') { move(atof(argv[i+1]), atof(argv[i+2])); usleep(30000); i += 2; }
      btn(1); usleep(15000); btn(0);
    }
    else if (!strcmp(argv[i], "down")) btn(1);
    else if (!strcmp(argv[i], "up")) btn(0);
    else if (!strcmp(argv[i], "key")) { key(atoi(argv[++i])); }
    else if (!strcmp(argv[i], "kd")) { org_kde_kwin_fake_input_keyboard_key(fi, atoi(argv[++i]), 1); flush(); usleep(8000); }
    else if (!strcmp(argv[i], "ku")) { org_kde_kwin_fake_input_keyboard_key(fi, atoi(argv[++i]), 0); flush(); usleep(8000); }
    else if (!strcmp(argv[i], "wheel")) { org_kde_kwin_fake_input_axis(fi, 0, wl_fixed_from_double(atof(argv[++i]))); flush(); usleep(20000); }
    else if (!strcmp(argv[i], "type")) {
      for (char *p = argv[++i]; *p; p++) { int sh; int c = code(*p, &sh); if (!c) continue;
        if (sh) { org_kde_kwin_fake_input_keyboard_key(fi, 42, 1); flush(); }
        key(c);
        if (sh) { org_kde_kwin_fake_input_keyboard_key(fi, 42, 0); flush(); } }
    }
    else if (!strcmp(argv[i], "sleep")) usleep(atoi(argv[++i]) * 1000);
    /* touch DOWN|MOVE ID X Y, touch UP ID: one contact through the compositor's touch path */
    else if (!strcmp(argv[i], "tdown")) { org_kde_kwin_fake_input_touch_down(fi, atoi(argv[i+1]), wl_fixed_from_double(atof(argv[i+2])), wl_fixed_from_double(atof(argv[i+3]))); org_kde_kwin_fake_input_touch_frame(fi); flush(); i += 3; usleep(16000); }
    else if (!strcmp(argv[i], "tmove")) { org_kde_kwin_fake_input_touch_motion(fi, atoi(argv[i+1]), wl_fixed_from_double(atof(argv[i+2])), wl_fixed_from_double(atof(argv[i+3]))); org_kde_kwin_fake_input_touch_frame(fi); flush(); i += 3; usleep(16000); }
    else if (!strcmp(argv[i], "tup")) { org_kde_kwin_fake_input_touch_up(fi, atoi(argv[++i])); org_kde_kwin_fake_input_touch_frame(fi); flush(); usleep(16000); }
  }
}
int main(int argc, char **argv) {
  dpy = wl_display_connect(NULL);
  if (!dpy) { fprintf(stderr, "no wayland display\n"); return 2; }
  struct wl_registry *r = wl_display_get_registry(dpy);
  wl_registry_add_listener(r, &rl, NULL);
  flush();
  if (!fi) { fprintf(stderr, "no org_kde_kwin_fake_input global\n"); return 3; }
  org_kde_kwin_fake_input_authenticate(fi, "ui4me-alpha-test", "automated alpha input"); flush();
  if (argc > 1 && !strcmp(argv[1], "serve")) {
    char line[4096];
    while (fgets(line, sizeof line, stdin)) {
      line[strcspn(line, "\n")] = 0;
      char *av[64]; int n = 1; av[0] = "fakeinput";
      char *tok = strtok(line, " ");
      while (tok && n < 60) {
        av[n++] = tok;
        if (!strcmp(tok, "type")) { char *rest = strtok(NULL, ""); if (rest) av[n++] = rest; break; }
        tok = strtok(NULL, " ");
      }
      run(n, av);
      printf("ok\n"); fflush(stdout);
    }
    return 0;
  }
  run(argc, argv);
  return 0;
}
