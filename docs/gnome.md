# GNOME 51 in voidlab

What the overlay changes to run GNOME 51 on Void, why, and how it is checked.
Reviewed on 2026-10-21 against void-packages `48066ac6` (2026-10-16), the
published `repo` release and upstream PR
[void-linux/void-packages#59394](https://github.com/void-linux/void-packages/pull/59394).

## Stock branch (`gnome51`)

The upstreamable version of this work is the `gnome51` branch of
`mendescotta/void-packages`, in `~/Projects/voidlab/void-packages`. It
carries no overlay changes and runs on Void's platform libraries: gtk4 4.22,
glib 2.88, accountsservice 23 and elogind 252. Its README describes the
patchset and has the install instructions (`./install-gnome51.sh`, or
`xbps-src` by hand). The session design is the one described below, without
the dinit/turnstile parts.

How it differs from the overlay:

- gnome-control-center and gnome-initial-setup stay at 50.0, and nautilus
  stays at 50.2.2. Their 51 releases need gtk4 4.24 and glib 2.89+, and the
  branch does not bump gtk4.
- gnome-desktop 51.0 is built without the gnome-desktop-gtk3 split. It keeps
  upstream's `libgnome-desktop-3.so.21`; the overlay listed `.so.20`, which
  does not match upstream. gnome-shell 51 imports `GnomeQR` at runtime, so
  gnome-desktop 44 gives a black greeter. xbps cannot see that dependency.
  The overlay hid it because it always had gnome-desktop 51.
- GnomeRR was removed upstream (`c030c776`, 51.alpha). The packages that
  still use it, plus gnome-flashback, are removed on the branch and added to
  `removed-packages`: all of Budgie with magpie, gnome-screensaver, and
  gnome-flashback. openbox no longer ships its GNOME session. cheese, eog,
  evince, evolution, gnome-panel, totem and xdg-desktop-portal-gtk are
  revbumped.

Bare-metal test (2026-10-23): the gdm 51 greeter comes up on runit with
NVIDIA. Login, power-menu and logout checks are in progress.

## Why Void is still on GNOME 48

Void ships GNOME 48 (gnome-shell 48.7, gdm 48.0, gnome-session 48.0). The
blocker, as oreo639 explains in #59394, is gnome-session: since 49 it brings
the session up only by starting systemd user units
(`gnome-session-init-worker` calls `org.freedesktop.systemd1.StartUnit`), and
gdm 49+ needs that newer gnome-session. elogind does not implement
`systemd1`.

PR #59394 ("[WIP] GNOME 50", open since 2026-03-16) updates Shell, Mutter,
Settings Daemon, Control Center and the leaf packages to 50, but keeps
gnome-session and gdm at 48 with compatibility patches:

| PR patch | Purpose |
|---|---|
| gdm `gsd-50.patch`, gnome-session `drop-gsd-wacom.patch` | stop requiring the removed Wacom gsd plugin |
| gsd `desktop-files.patch` | restore the `.desktop` files gnome-session 48 starts plugins from |
| gnome-shell `revert-remove-gsm.patch` | Shell registers with gnome-session again and ships its `.desktop` file |
| gnome-shell `elogind-sd_notify.patch` | real `sd_notify()` through elogind |
| gnome-shell `sysd-service.patch` | install the Shell's user unit without systemd |

The PR states its known problems: shutdown and suspend are missing (the
`CanShutdown()`/`CanSuspend()` return type changed after 48), the Shell is
always "Not Responding" at logout, gdm stays at 48, and gnome-initial-setup
is not adapted. The discussion also covers:

- gnome-session-openrc (swagtoy). It replaces the leader, but it works only
  with OpenRC.
- gnome-session-shepherd. oreo639 got it working, but it reimplements
  gnome-session and is incomplete: without `RegisterClient`, gsd-xsettings
  fails and scaling breaks.
- Terromur's GNOME 51 templates, with a gnome-session patch that fixes
  reboot, shutdown and logout.
- runit has no dependency ordering, so a runit-managed user session is a
  poor fit.

voidlab does it differently: everything is GNOME 51, gnome-session and gdm
included. Only the one systemd-only part is replaced: gnome-session's init
worker. Neither runit nor dinit manages the session. This avoids the PR's
48/50 API mismatches (the Chimera comparison in
`void-dinit-iso/docs/gnome-services.md` reaches the same conclusion).

## The session without systemd

- **gnome-session** is built with `-Dsystemd=false`
  (`01-systemd-optional.patch`). It sets up and exports the session
  environment, then execs `/usr/libexec/gnome-session-init-worker <session>`.
- **`files/gnome-session-init-worker`** (bash) replaces upstream's
  systemd-only worker. It starts the same components, in the order the
  units used, as plain children of the login session:
  1. `gnome-session-service`.
  2. `gnome-shell` (`--mode=gdm`, `initial-setup` or `user`). The worker
     picks the Wayland socket name itself, so it can hand it to the plugins.
  3. A `dbus-monitor` waits for the Shell's own
     `RegisterClient(org.gnome.Shell.desktop)`, then calls `Initialized`.
     This is what `gnome-session-signal-init.service` does upstream.
  4. The `gsd-*` plugins.

  If gnome-session-service or the Shell exits, the session ends. A plugin
  that fails is restarted up to 5 times (`Restart=on-failure`). The worker
  skips plugins whose system daemon is missing (cupsd, pcscd,
  usbguard-daemon, ModemManager), and per-session opt-outs go in
  `/etc/gnome-session/sessions/<session>.disabled`. A lock refuses a second
  concurrent session for the same user. At logout, the worker clears the
  display variables from the D-Bus activation environment, as the Shell
  unit's `ExecStopPost` does.
- **`files/sessions/gnome-login`** lists the components for gdm's greeter
  session (the components that gdm's `gnome-session@gnome-login.target`
  drop-in requires).
- **`files/dbus-run-session-if-needed`** wraps `gnome.desktop`'s `Exec`.
  gnome-session ≥ 49 aborts without a session bus; gdm provides one, but
  other display managers (lightdm) and `startx`-style logins do not.
- **gnome-shell `revert-remove-gsm.patch`** keeps only the `main.js` hunk:
  the Shell calls `RegisterClient` once it is ready. That call is the
  readiness signal the worker waits for.

The worker is the same on runit and dinit. The only init-specific code in
it is `user_manager`, which runs only when turnstile's user dinit socket
exists (see below).

## runit and dinit

The packages are the same for both inits. What differs is service
supervision and the user-session plumbing, and that lives outside the
GNOME templates.

| | runit (stock Void) | dinit (dinit-void) |
|---|---|---|
| system services | runit service directories in `/etc/sv` (`gdm/files/gdm`, `elogind/files/elogind`, installed by the templates), enabled with `ln -s /etc/sv/<name> /var/service/` and managed with `sv` | `dinit-void/void/{gdm,elogind,dbus,polkitd,upower}.service`, `dinit-dm` helper |
| elogind start | runsv; D-Bus activation goes through `elogind.dbus-activate`, which hands off to `sv start` | dinit; `elogind.dbus-activate` hands off to `dinitctl start elogind` |
| session bus | from `gdm-wayland-session` (or `dbus-run-session-if-needed`) | turnstile's user dinit runs a shared bus (`/usr/libexec/gnome-session/user-dbus`, ISO overlay) |
| PipeWire | XDG autostart in the session (Void handbook layout) | user dinit services in `/usr/lib/dinit.d/user/boot.d` (ISO overlay) |
| turnstile | not used | `turnstiled` before `loginready`; `pam_turnstile` after `pam_elogind` (ISO hook) |
| graphical target | n/a | the worker starts/stops turnstile's `graphical.target` and sets `WAYLAND_DISPLAY` in the user manager |
| elogind patch | not needed | `turnstile-manager-no-session.patch` (below) |

Init-related changes in the templates, and which init needs them:

- `elogind/files/elogind.dbus-activate` (both inits). At boot, an elogind
  started by D-Bus activation could win the race against the supervised
  one, which then loops (runit) or makes gdm fail (dinit). The script hands
  the start to the supervisor instead.
- `elogind/patches/turnstile-manager-no-session.patch` (dinit + turnstile
  only; no effect without turnstile). turnstile gives each user manager its
  own elogind session, so D-Bus-activated apps were attributed to it.
  Processes in a `turnstiled` session are now reported as outside any
  session, as systemd does for `user@.service`. polkit and gdm then fall
  back to the display session.
- gdm `greeter-env-without-systemd.patch` (both inits). Since gdm 50, the
  greeter environment goes only to `environment.d`, which is for
  `systemd --user`. The patch sets it on the session directly again.
- gdm `pam-turnstile-elogind.patch` is inherited from Void unchanged. It
  puts `pam_turnstile` *before* `pam_elogind`; the dinit ISO hook moves it
  after (`void-dinit-iso/hooks/post_rootfs_gnome.sh`), because elogind must
  create `/run/user/<uid>` first (`manage_rundir = no`).
- Tried and dropped (2026-10-19, `24a1e7d`, `944566b`, `7c99134`): runit
  service directories and dinit units for each session component
  (`files/runit-services`, `files/dinit-session`, `dinit-component`). Running
  the Shell under a user service manager moves it out of the login session,
  which gave a blank greeter and no polkit agent. The PR's gsd
  `desktop-files.patch` and the `.desktop` half of
  `revert-remove-gsm.patch` went with them: only gnome-session 48 needs
  them.

## Patches

`A` = added by voidlab, `C` = Void's patch changed, `V` = Void's patch kept
unchanged, `D` = Void's patch dropped.

### Session and login

| package | patch / file | | what it addresses |
|---|---|---|---|
| gnome-session | `01-systemd-optional.patch` | A | `-Dsystemd=false`: no systemd units, no `leader-systemd.c` worker, no `gnome-session-ctl`; libelogind instead of libsystemd |
| gnome-session | `05-autostart-condition.patch` | A | 49 dropped `AutostartCondition` (systemd's xdg-autostart generator evaluates it). Without that, Orca and other conditional autostarts launched at every login. Evaluates GSettings, if/unless-exists and GNOME3 if/unless-session again |
| gnome-session | `files/gnome-session-init-worker`, `files/sessions/gnome-login`, `files/dbus-run-session-if-needed` | A | the non-systemd session (above) |
| gnome-shell | `revert-remove-gsm.patch` | A | Shell calls `RegisterClient` when ready, the worker's readiness signal |
| gnome-shell | `sysd-service.patch` | A | installs `org.gnome.Shell*.service` user units even with `-Dsystemd=false` (inert metadata) |
| gnome-shell | `no-exe-introspection.patch` | V | executable introspection segfaults on musl |
| gnome-shell | `gjs-1.86.0.patch` | D | merged upstream by 51 |
| gdm | `greeter-env-without-systemd.patch` | A | greeter environment (DCONF_PROFILE, XDG_*) reaches the greeter without systemd --user |
| gdm | `pam-turnstile-elogind.patch` | V | `pam_turnstile` in the launch-environment stack |
| gdm | `drop-wayland-udev-rules.patch` | D | in 51.1 (reverse-applies) |
| gdm | `INSTALL` | changed | creates the preallocated `gdm-greeter` account (gdm 49+ without userdb looks up exactly that name; `system_accounts` cannot create names with a dash) in group `gdm`, for the PAM `user ingroup gdm` check; drops the `/var/lib/gdm/.pam_environment` XDG_RUNTIME_DIR hack |
| elogind | `turnstile-manager-no-session.patch` | A | see runit and dinit |
| elogind | `fix-kexec-pass-e-flag.patch` | A | upstream fix: `kexec` without `-e` only loaded the kernel |
| elogind | `missing-stat.patch`, `netlink-if_tunnel-include-order.patch` | A | 257 build fixes (missing `sys/stat.h`; kernel-headers 6.14 `if_tunnel.h` needs `linux/ip.h` first) |
| elogind | `shared-always-build-user-record-nss.patch` | A | `-Dnss-elogind=false` failed to link (elogind#365) |
| elogind | `gshadow.patch`, `sigfillset.patch` | C | rebased for 257 (`src/shared/async.h`; `gshadow.h` only on glibc) |
| elogind | `getdents.patch`, `id-nobody.patch` | V | musl getdents64; Void's nobody is 99 |
| elogind | `musl-basename`, `rlim-cur`, `SEEK_DATA`, `statx`, `strerror_r`, `strerror_r_1`, `tests` | D | Void's 252 patches, not needed by 257 on glibc. **musl is not built or tested** for elogind 257 |
| elogind | `files/elogind.dbus-activate` | A | see runit and dinit |
| accountsservice | `machine-id-fallback.patch` | A | Void may lack `/etc/machine-id`; read `/var/lib/dbus/machine-id` instead of aborting |
| accountsservice | `ad0365b7…`, `fix-build`, `fix-tests`, `mocklibc-Fix-compiler-warning`, `musl-fgetspent_r` | D | `ad0365b7` is in 26.27.3; the others no longer apply (tests disabled with `-Dtests=false`). musl not covered |

### Shell, settings, apps

| package | patch | | what it addresses |
|---|---|---|---|
| gnome-control-center | `grd-systemd.patch` | C | rebased for 51; keeps the Remote Desktop page visible without systemd's unit state |
| nautilus | `0001-add-parent-folder-button.patch` | A | local UI choice: an "Open Parent Folder" button |
| nautilus | `skip-thumbnails-test.patch` | D | test file gone in 51 |
| xdg-desktop-portal-gtk | `session-only.patch` | A | `-Dsession-only` builds only the GTK-free Inhibit and Email portals (`xdg-desktop-portal-gtk-session`), so xdg-desktop-portal-gnome does not pull GTK3 |
| gnome-keyring | `sys-select-h.patch` | V | `FD_ISSET` include |
| gcr | `Fix-FTBFS-on-x32.patch` | V | x32 build |
| mutter | `565756e1….patch` | D | in 51.1 (reverse-applies) |
| sushi | `66.patch` | D | sushi 51 is a GTK4 rewrite (not re-checked against the tarball) |
| file-roller | `fix-symlink-handling-7zip.patch` | D | fixed upstream differently (44.7 passes `-snl`) |
| gthumb | `build-order.patch`, `cross-x11-check.patch`, `README.voidlinux` | D | gthumb 4.0 is a GTK4 rewrite |

### Platform

| package | patch | | what it addresses |
|---|---|---|---|
| glib | `0001-Relocate…`, `glib-compile-schemas-remove-deprecated-warnings`, `gobject_init_on_demand`, `quark_init_on_demand` | V | GI repository relocation, schema warnings, musl ctor order |
| glib-bootstrap | the same four, through `patches -> ../glib/patches` | V | the symlink was lost when the overlay replaced the directory; restored in 2.90.1_2 |
| gtk4 | `remove-failing-tests.patch` | V | undocumented-symbol doc tests |
| gtk4 | `fix-vulkan32bit.patch` | D | in 4.24.1 (reverse-applies) |
| gtkmm4 | `setlocale-sigsegv.patch` | V | `std::locale(std::setlocale(...))` segfaults; use `std::locale("")`. Lost with the overlay, restored in 4.24.0_2 |
| gdk-pixbuf | `largejpeg-oom-test.patch` | D | test-only, code changed in 2.44 |
| gjs | `ignore-encoding-test.patch` | V | musl |
| libsecret | `remove-test-collection.diff` | V | flaky test |
| localsearch | `sqlite-seccomp.patch` | V | F2FS ioctl under seccomp |
| tinysparql | `disable-cli-test.patch`, `gh-ci-timeout.patch` | V | CI |
| evolution-data-server | `fix-boost`, `gen-tables`, `gir`, `skip-broken-tests` | V | libphonenumber found without a boost_thread probe, table generators built for the host (cross), g-ir-scanner keeps LDFLAGS, flaky migration test skipped. Lost with the overlay, restored in 3.56.2_7 |
| gst-plugins-base1 | `sndio.patch` | D | still applies; dropped with the (default-off) `sndio` option and the `update` file |
| pam | `no-examples.patch` | D | replaced by meson `-Dexamples=false` |
| eudev | `clock-group-for-ptp-rtc.patch` | A | systemd's PTP/RTC `clock` group rules (with `system_groups="render clock"`) |
| eudev | `78-sound-card.rules.patch` | D | in 3.2.15 (reverse-applies) |
| sd-tools | `compound-literal-scope`, `gcc`, `glibc-getdents64` | A | dinit images only (tmpfiles crash, rlimit include, glibc getdents) |
| common | `environment__setup__misc.sh.patch` | A | `NONGNU_SITE` mirror |

## Dependency bumps, rebuilds and splits

GNOME 51's own requirements force the platform bumps:

| bump | required by |
|---|---|
| glib 2.88 → 2.90, gtk4 4.22 → 4.24, pango 1.56 → 1.58 | libadwaita 1.10 (`glib >= 2.89.3`, `gtk4 >= 4.23.1`), nautilus 51 (`gtk4 >= 4.24`); gtk4 gained explicit `glib>=2.90`/`pango>=1.58` runtime depends because the SONAMEs did not change |
| libadwaita 1.9 → 1.10, gjs 1.88 → 1.90, gsettings-desktop-schemas → 51 | Shell 51 (`gjs >= 1.87.1`, schemas `>= 51.beta` in gsd) |
| accountsservice 23.13 → 26.27.3 (**SONAME .0 → .1**) | gnome-control-center 51 (`>= 26.27.3`) |
| elogind 252 → 257 | gdm 51 (`sd_session_get_username()`) |
| gnome-desktop 44 → 51 (**libgnome-desktop-3 .20 → .21, libgnome-rr-4 removed**) | Shell/Mutter/g-c-c 51 |
| mutter 48 → 51 (libmutter-16 → 51) | Shell 51 |
| gdk-pixbuf 2.44, at-spi2-core 2.62, dconf 51, gvfs 1.62, gnome-online-accounts 3.58, libportal 0.11, libsecret, tinysparql/localsearch 3.12, GStreamer 1.28.8 | coordinated GNOME 51 platform (`c97dfb5`, `213da13`) |
| pam 1.5.3 → 1.7.3, eudev 3.2.14 → 3.2.15 | **nothing in GNOME 51** (imported from a separate `pam-1.7.3` branch) |

Rebuilds at the same version, for our SONAMEs: `xdg-desktop-portal-gtk`
(libgnome-desktop-3.so.21), `xfce4-whiskermenu-plugin`
(libaccountsservice.so.1); see `tools/keep-overlay.list`.

GTK3 splits, so that GNOME core does not pull in GTK3 (the image hooks
reject GTK3 ELF objects):
`gcr-base` (libgck, libgcr-base), `libnma-gtk4` + `libnma-common`,
`colord-gtk4`, `gnome-desktop-gtk3`, `evolution-data-server-core` /
`-gtk3` (EDS without WebKit OAuth), `ibus-ui-gtk3` (GNOME runs ibus with
`--panel disable`), `gst-plugins-good1-gtk3`, `libdecor-gtk`,
`xdg-desktop-portal-gtk-session`. Optional features turned off to keep the
dependency set small: gtk4 media-gstreamer/broadway/cloudproviders/colord,
gvfs goa/onedrive (`gvfs-goa` added to `removed-packages`),
gst-plugins-good1 libcaca/aalib, nautilus cloudproviders.

Build-cycle break: gnome-shell imports the Gdm typelib, but gdm needs
gnome-shell. So `libgdm` ships the typelib and `org.gnome.login-screen`
schema, `gnome-core` depends on `libgdm`, and gdm reaches Shell and Session
through the `gdm-session` metapackage.

Pins: ibus stays at 1.5.32. 1.5.34's gtk4 immodule recurses in
`g_object_new` under gtk4 4.24 and aborts every GTK4 app.
evolution-data-server stays at 3.56.2 for a coordinated ABI move.

`gnome-core` behaves differently from Void's: it no longer depends on gdm,
gnome-initial-setup, gnome-settings-daemon (now pulled by gnome-session),
yelp, zenity, sushi, tinysparql, gnome-user-docs, gnome-shell-extensions or
gnome-themes-extra. Install `gdm` explicitly.

## Review findings (2026-10-21)

Install checks ran against the published release: an empty rootfs, Void's
repo plus `repo`, `bestmatching=true` as the README says.

**Breaks a fresh install:**

- `gnome-core` no longer pulled `adwaita-icon-theme` (Void's does). Nothing
   else in the stack depends on it, so a `gnome-core` install had blank
   status icons and no visible power or lock buttons. Fixed in
   gnome-core 51.0_8.

**Breaks Void packages once the voidlab repo is enabled:**

1. Bumped SONAMEs without rebuilding their Void consumers. These become
   uninstallable, and an `xbps-install -Su` on a system that has them
   aborts:
   - `libgnome-desktop-3.so.20`: evolution, budgie-desktop,
     budgie-session, budgie-screensaver, budgie-control-center,
     gnome-flashback, gnome-screensaver.
   - `libaccountsservice.so.0`: mate-control-center (so `mate`),
     budgie-control-center.
2. `evince-48.4_1` (our template) was built before the gnome-desktop-gtk3
   split. Its `run_depends` say `gnome-desktop>=51.0_1`, but it needs
   `libgnome-desktop-3.so.21`, which now lives in gnome-desktop-gtk3. It
   cannot be installed. Rebuilt as 48.4_2.
3. Orphans in the release (no template on `main`) that still win over Void
   under bestmatching:
   - `libtotem-43.2_4`: same gnome-desktop problem, so it breaks `totem`
     and `gnome-apps`.
   - `cheese`/`libcheese 44.1_6`, `gnome-panel 3.58.1` (cannot be
     installed), `gprbuild` (needs gcc 16 `libada`).
   - Older than Void, so harmless but stale: `Thunar 4.20.9`,
     `flatpak 1.18.3`, `dinit 0.22.1_1`, `cargo-auditable`.
4. With bestmatching, the repo is not opt-in per package. `base-system`
   alone takes voidlab's pam 1.7.3 and eudev 3.2.15, and firefox takes ~12
   voidlab libraries. Without bestmatching, xbps mixes 48 and 51 (gdm,
   gsd, gnome-session and glib from Void, Shell 51), which cannot work.

**Template and repo hygiene:**

5. The overlay replaces a template's whole directory, which silently drops
   Void patches: `glib-bootstrap` (its `patches` symlink and `update`),
   `gtkmm4` `setlocale-sigsegv.patch`, and evolution-data-server's four
   patches (all restored). Also dropped: the `update` files of gst-plugins-base1,
   gstreamer1, gtkmm4 and glibmm2.68, which keep `xbps-src update-check` on
   stable series (here, each replaced by `ignore=` or nothing).
6. `common/shlibs` still maps the archived gcc 16 libraries (`libgo.so.25`,
   `libgphobos.so.7`, `libgdruntime.so.7`, `libgnat-16`, `libgnarl-16`) and
   mutter 50's `libmutter-*-18` SONAMEs. Removed.
7. `gnome-disk-utility` ships `51.beta`, and its `distfiles` hardcodes `/51/`.
8. `gnome-control-center` shows the Remote Desktop page unconditionally,
   but `gnome` no longer depends on gnome-remote-desktop.
9. The last paragraph of `01-systemd-optional.patch` says a replacement
   worker "is still required"; `files/gnome-session-init-worker` is that
   worker. `sysd-service.patch` says "runit". `revert-remove-gsm.patch` has
   no voidlab-specific explanation.
10. `PACKAGES.md` is stale (gdm 51.0_3, gnome-session 51.0_11; now 51.1_2
    and 51.0_15).
11. `gst-plugins-good1` moves `qmake_default_version` from where Void
    places it, which triggers an xlint exception. A gratuitous diff.
12. Known gaps: `gsd-xsettings` is not started (X11 apps under Xwayland get
    no XSETTINGS), and elogind 257, accountsservice 26 and glib-bootstrap
    are not tested on musl.

xlint over the GNOME templates reports only the two findings tolerated in
`tools/xlint-known.txt`.

## Compiler

Nothing needs gcc 16. CI builds with Void's gcc 14.2.1, and the binaries
need at most `GLIBCXX_3.4.32`, which Void's libstdc++ 14 provides. gthumb
4.0 assumes C23 and gets `-std=gnu23`. gtk4 4.24.1_3 and accountsservice
26.27.3_2 were built with the archived gcc 16 and are rebuilt (`_4`, `_3`).
`gprbuild` in the release needs gcc 16's `libada` and has no template.

## Fresh install test (2026-10-21)

A stock runit Void install, not an ISO. The disk image is in
`/var/tmp/voidlab-gnome-test/`.

1. `xbps-install -S -r <root> base-system grub gnome-core gdm
   NetworkManager`, with Void's repo and the published `repo`
   (`bestmatching=true`): 469 packages, 61 from voidlab, `xbps-pkgdb -a`
   clean.
2. Enabled dbus, NetworkManager and gdm, as in the Void handbook. Booted
   under QEMU/KVM (virtio-gpu).

| check | result |
|---|---|
| greeter | no GPU at first: `mesa-dri` is not pulled in. That's expected, the handbook installs drivers separately. After `xbps-install mesa-dri`, the GDM 51 greeter (gdm → gdm-wayland-session → `gnome-session-init-worker gnome-login`) shows |
| status icons | **missing** in the greeter and the session (empty quick-settings button, blank power and lock buttons): `adwaita-icon-theme` is not installed. Installing it fixes them |
| login | works; elogind session class `user`; Shell, Xwayland and 10 gsd plugins run as children of the worker |
| power menu | Suspend, Restart and Power Off present (the PR's `CanShutdown` problem does not occur) |
| Restart | the confirmation dialog, then elogind → runit stage 3 → reboot |
| logout | `gnome-session-quit --logout`: no user processes left, `/run/user/1000` removed, back at the greeter, and a second login works. No "Not Responding" |
| lock / unlock | Super+L, then unlock with the password |
| polkit | Settings → Users → Unlock shows the Shell's agent; authentication succeeds (accountsservice 26) |
| apps | Files (with the parent-folder button) and Settings run |
| not running | `ibus-daemon` (Shell logs "Unable to connect to ibus"; input methods are unavailable), `gsd-xsettings` (by design), sound (no PipeWire; the handbook installs it separately) |

No JS errors in `~/.cache/gdm/session.log`. "Locale not supported" comes from
the test image's unconfigured glibc-locales, not from GNOME.

## Bare-metal test of the stock branch (2026-10-23)

This host (NVIDIA laptop) running `gnome51` packages (gnome-shell/mutter
51.1, gnome-session 51.0, gdm 51.1, g-c-c 50.0) on the overlay's glib 2.90,
gtk4 4.24 and elogind 257. Logs from `/usr/local/sbin/gnome-validate-log`.

| check | result |
|---|---|
| poweroff from the session menu | clean: the Shell exits, gdm briefly respawns a greeter, which gets SIGTERM; runit stage 3 leaves only kernel threads. The only teardown noise is a Gjs-CRITICAL on a disposed `KeyboardBrightnessToggle` |
| greeter init worker | after the per-pid `wait` fix, greeter.log stays small (4.8K vs 2.5 GB before) and no worker spins after login |
| boot → greeter → login | works, gdm debug lines reach socklog |
| Nautilus cold start | ~0.5 s: the first portal setting is read 62 ms after exec. The ~25 s portal stall seen earlier did not come back |
| autostart | gnome-session 51 skips every autostart entry with `X-GNOME-Autostart-Phase` ("no longer manages session services"): gnome-keyring pkcs11/secrets/ssh, at-spi-dbus-bus, xdg-user-dirs. Result: no SSH agent, no `xdg-user-dirs-update`, and an extra D-Bus-activated keyring daemon. **Fixed** (gnome51 eecb9bbf66, overlay 1fd2ef9 revision 17): outside the greeter the init worker runs `xdg-user-dirs-update` and `gnome-keyring-daemon --start --components=pkcs11,secrets,ssh`, and exports `SSH_AUTH_SOCK`. at-spi is left to D-Bus activation, as upstream's `at-spi-dbus-bus.service` |
| GOA | evolution-source-registry timed out on `org.gnome.OnlineAccounts`. Cause: the local stub `Exec=/bin/true`. dbus-daemon takes exit 0 as "forked" and waits out its 25 s activation timeout. Local fix: the stubs now run `/bin/false`, so activation fails in milliseconds |
| polkit, Nautilus | fine (user) |
| suspend | not configured on this host |

Still to check: lock/unlock, logout → second login (also confirms
`SSH_AUTH_SOCK` in the session and a single keyring daemon), Settings (g-c-c
50 on 51 schemas). The teardown Gjs-CRITICAL is upstream gnome-shell's.
