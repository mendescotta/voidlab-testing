# COSMIC 1.11 packaging review

Reviewed against [Void PR #61599](https://github.com/void-linux/void-packages/pull/61599),
the [package manual](https://github.com/void-linux/void-packages/blob/master/Manual.md),
and [contribution guidelines](https://github.com/void-linux/void-packages/blob/master/CONTRIBUTING.md).
The work addresses technical packaging requirements. Maintainer acceptance still
requires builds and runtime testing; source checks alone do not establish that.

## Changes

- Updated all 29 active pop-os release templates, including pop-launcher and
  xdg-desktop-portal-cosmic, to epoch-1.11.0 with SHA-256 values calculated from
  downloaded archives. Updated both desktop metapackages to 1.11.0_1.
- cosmic-tweaks has its own release series. It stays at 0.2.5, revision 2,
  with the Cargo build style and explicit installation of its three assets.
  Its renamed upstream URL and stale archive checksum were also corrected.
  Archived cosmic-initial-setup is outside the active package set.
- Removed blanket x86_64 restrictions, optional per-template sccache wrappers,
  unused mold dependencies, and obsolete LLVM version dependencies. Host
  bindgen dependencies use the default clang and libclang packages. Other architectures
  are enabled for testing, not claimed as tested.
- Kept the Cargo build style and upstream asset installation recipes.
  cosmic-workspaces-epoch now uses Cargo's locked, explicit target build;
  its Makefile only installs assets. Removed the compositor's incorrect extra
  session-file installation; cosmic-session owns the session entry.
- Fixed wallpaper extraction. Removed the store's redundant tag variable and
  explicitly selected its non-systemd desktop features.
- Disabled the separate systemd features in cosmic-session and notifications.
  The greeter patch separates logind from systemd and disables the daemon
  dependency's default features, replacing large logger-removal patches.
- Greeter binaries and configuration use Void install helpers. Removed the
  justfile patch, protected greetd configuration with conf_files, and based PAM
  on system-local-login without duplicate session modules. The runit service
  no longer kills elogind processes or requires separately supervised elogind.
- Removed both metapackage INSTALL hooks: they changed shared COSMIC files,
  per-user directory settings, and PipeWire configuration during installation.
  Audio and login instructions are installed with cosmic-session and the greeter.
- Removed custom keyboard shortcuts and the session runtime-directory bootstrap;
  PAM/elogind provides runtime directories. Removed the default-log-level patch
  and stale backup patch. GSettings schema compilation uses the package trigger.
- Removed the panel hook that fetched and modified an arbitrary checkout in the
  shared Cargo cache. A future fix for its dependency's disconnect behavior
  needs a pinned, reproducible dependency patch or an upstream correction.
- Refreshed the retained patches against 1.11.0. Each states why it exists,
  upstream status, and when to drop it. Patches apply without fuzz or offsets.

## Licensing

Reviewed Rust SPDX identifiers, Cargo metadata, Debian copyright files and
top-level licenses from the release archives. Kept GPL-3.0-only where source
identifiers are narrower than Cargo's GPL-3.0-or-later declaration. Added
MPL-2.0 to cosmic-applets, cosmic-files, cosmic-osd and cosmic-settings-daemon
for their MPL source files. Existing mixed licenses in settings, panel and
pop-launcher remain. Artwork and sounds retain CC-BY-SA-4.0.

Upstream still needs to reconcile metadata inconsistencies, notably in osd,
settings-daemon and the portal. This is not an upstream license clarification.
The source checker's JSON report records source identifier counts for review.

## Verification and reuse

Run from this repository:

```sh
python3 tools/cosmic-sources.py
python3 tools/check-cosmic-cargo-cache.py
python3 tests/test-cosmic-sources.py
xlint srcpkgs/cosmic*/template srcpkgs/pop-launcher/template \
    srcpkgs/xdg-desktop-portal-cosmic/template
```

The checker includes cosmic-tweaks at its independent version. It downloads
missing archives, verifies checksums, extracts into its
own cache and applies patches sequentially with zero fuzz. It rejects line
offsets and records license identifiers. It never changes Cargo's shared cache.
With `--just /path/to/just`, it also parses upstream installation recipes using
`--dry-run`. This checks recipe arguments, not the existence of build outputs.

Use `--version 1.12.0` to review a future release. Add `--update` to write the
coordinated versions and checksums only after every archive and patch passes.
The default persistent cache and report are in hostdir/cosmic-source-review.
`--cache` selects another location. Python 3.12+, curl and patch are required.
The offline tests verify checksum rejection, patch application, offset rejection
and preserving independently versioned packages.

For this review, all 30 checksums, nine patches, and 25 upstream just installation
recipes passed. xlint, template Bash parsing, runit shellcheck and patch whitespace
checks passed. Icons, wallpapers and sounds were installed into isolated staging
directories using upstream recipes. Artifacts are in the workspace's
out/cosmic-1.11-review directory.

Full xbps-src builds, installation and login/audio/lock/logout tests remain to
be done, including glibc, musl and aarch64 coverage. cosmic-monitor requires at
least Rust 1.95; several other components require 1.93. COSMIC Settings still
selects its upstream systemd service-manager backend; upstream only offers
systemd or OpenRC. Its service-management controls need separate work for Void.
The retained theme and login patches also need runtime checks and, where
applicable, upstream reports. A Void submission should use one commit per
package with the repository's commit subject convention.

## Follow-up patch audit and local builds

The settings-daemon readiness polling patch was dropped after inspecting
cosmic-config at libcosmic commit 430f3d48a97d8779f9c1985473912e594ccca1ae,
the revision pinned by cosmic-settings 1.11.0. Its watcher subscription retries
failed registrations with exponential backoff. The extra session-side poll
only suppressed startup messages and could delay the entire desktop by five
seconds; it was redundant rather than an upstream fix newly landed in 1.11.

The other nine patches still address code/configuration present in 1.11:

| Package | Patches retained | Evidence |
| --- | --- | --- |
| cosmic-comp | Corner-radius redraw | All four protocol handlers remain empty. |
| cosmic-greeter | D-Bus account, greetd command/account, PAM, mode detection | Upstream still uses cosmic-greeter and Debian PAM includes. |
| cosmic-greeter | Decouple logind/systemd | logind enables systemd, and the daemon dependency enables defaults. |
| cosmic-greeter | Session picker | Confirming the same username still restores the saved session. |
| cosmic-session | Wait for active login session | KMS skips inactive sessions; backend initialization still requires an output. |
| cosmic-settings | Theme schema defaults | Theme v2 still requires list_button and the palette enum still requires its Dark variant. |

The session-picker patch now tracks the owner of the selected session separately
from the username editor. This preserves explicit choices on reconfirmation while
still restoring the saved default when a different username is typed manually.

`python3 tools/build-cosmic.py` builds and checks the complete active COSMIC set,
with logs and resumable fingerprints in hostdir/cosmic-build. `--jobs` controls
compilation concurrency. `--install` additionally previews an exact-version XBPS
transaction and updates the COSMIC packages captured as installed on its first
run, or installs cosmic-desktop when COSMIC is absent. It does not activate
services or switch display managers. The build helper forwards the job limit
explicitly to xbps-src with -j; setting XBPS_MAKEJOBS in its environment alone
does not reliably survive xbps-src's environment initialization.

The applets template selects `--package cosmic-applets`: upstream installs this
combined executable and aliases, so compiling every standalone workspace binary
is redundant. `--resume-package cosmic-applets` can reuse a preserved build tree
when only its single-line configure_args selection changed. The tool rejects
resuming after archive, patch or other template changes. `--status` reports
checkpoints and the latest log; competing xbps-src builds are waited out.

The greeter's pam-sys build uses clang-sys with direct linking rather than
runtime loading. It needs the unversioned libclang linker name from
clang23-devel, libclang23, and LLVM_CONFIG_PATH pointing to llvm-config-23.
The default clang/libclang runtime packages alone do not provide that linker
name. These are host build dependencies, not target development dependencies.

The Cargo cache audit checks tracked files and submodule revisions against the
release lockfiles. It ignores Cargo's generated .cargo-ok markers and reports
dirty unused revisions separately. During this build, 47 fetched pinned
revisions were clean; the old cache-editing workaround survived only in an
unused older libcosmic checkout. The audit never changes cache contents.

`tools/restart-cosmic-build.py --pid <controller> --jobs 6` finishes the active
package before changing concurrency. It verifies successful completion,
unchanged sources and exact repository metadata before recording a checkpoint
and restarting. It preserves the controller's --install option and uses Linux
pidfds when signaling the controller. The active compiler is never stopped.
