# CLAUDE.md

Behavioral guidelines for LLM-assisted work on **slpkgs** — the package
collection for Sunlight Linux, a fork of
[void-packages](https://github.com/void-linux/void-packages) (`xbps-src`
templates), rebranded from Void to Sunlight Linux.

> Derived from [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)
> (MIT), based on [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876)
> on LLM coding pitfalls. Adapted for slpkgs: `xbps-src` template correctness,
> supply-chain caution, and keeping a small, mergeable delta from upstream
> void-packages.

> **Status:** early bootstrap. The repo will be based on a void-packages fork
> with the Sunlight rebrand. Upstream's `Manual.md`, `srcpkgs/`, `common/`, and
> `xbps-src` are authoritative for *how packaging works*.

**Tradeoff:** These guidelines bias toward caution over speed. Templates run
shell on builders and decide what lands in users' systems (supply chain), and a
large rebrand delta makes every upstream sync painful. When in doubt, match
upstream and ask.

See [EXAMPLES.md](EXAMPLES.md) for concrete examples grounded in `xbps-src`
template scenarios.

---

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before editing a template:
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
  Packaging has many near-synonyms:
  - `depends` (runtime) vs `makedepends` (build, target) vs `hostmakedepends`
    (build, host).
  - `version` (new upstream release → also update `checksum`) vs `revision`
    (packaging-only rebuild).
  - a `build_style` (gnu-configure, cmake, meson, go, cargo, python3-module, …)
    vs hand-written `do_build`/`do_install`.
  - the main package vs subpackages (`-devel`, `-doc`, `*_package()`).
  Surface which is meant.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.
- **Check upstream parity first.** void-packages' `Manual.md` and the existing
  `srcpkgs/<similar>/template` almost always show the idiomatic way. Match it
  unless there's a documented reason to diverge.

## 2. Simplicity First

**Minimum template that builds the package. Nothing speculative.**

- Use a `build_style` instead of hand-rolling build/install steps when one fits.
- Don't add subpackages (`-devel`, `-doc`), options, or `configure_args` that
  weren't asked for and aren't needed.
- Don't vendor sources — use `distfiles` + `checksum`.
- Don't add `makedepends` "just in case"; add what the build actually needs.
- Keep `do_*` overrides to the minimum the build_style doesn't already handle.

Ask yourself: "Would a void-packages reviewer say this template is doing more
than it needs to?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess. Keep the upstream
delta small.**

When editing templates:
- Don't reformat or reorder template fields; void-packages has a conventional
  field order — keep it.
- Don't "improve" unrelated templates while changing one.
- **Bump `revision` on a packaging change; bump `version` + update `checksum`
  for a new upstream release.** Don't forget the checksum.
- Match shell style (the template is `sh`; quoting and `vinstall`/`vmkdir`
  helpers matter).

**slpkgs-specific — keep merges with upstream sane:**
- **The Sunlight rebrand is concentrated, not sprayed.** Branding changes live
  in a small set of packages (base-files, GRUB, efibootmgr, …). **Do not
  mass-`sed` `void` → `sunlight`** — package names, paths, mirrors, and module
  names that must match upstream stay as they are. A wide rename breaks builds
  and makes every future sync a conflict.
- Prefer changes that are upstreamable or trivially re-appliable over invasive
  forks of a template.

The test: every changed line traces to the request, and the diff against
upstream void-packages stays as small as it can be.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add package X" → "`./xbps-src pkg X` builds in a clean masterdir, `xlint` is
  clean, and the package installs."
- "Update X" → "`version`/`checksum` updated, it builds, and a smoke test
  passes."
- "Rebrand Y" → "Only the intended branding changed; X still builds and the
  package name/paths are unchanged."

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

**Verification in slpkgs:**
- `./xbps-src lint <package>` (`xlint`) — template lint.
- `./xbps-src pkg <package>` — build in a chroot/masterdir (the real test).
- Install / smoke-test the built `.xbps` (ideally in a VM) for runtime changes.
- `git diff` against upstream — confirm the rebrand delta stayed small.

Strong success criteria let you loop independently. Weak criteria ("make it
build") require constant clarification.

---

## slpkgs Project Context

### Positioning
- The Sunlight Linux package collection: a void-packages fork, rebranded
  Void → Sunlight, built with `xbps-src`.
- Produces the base system and repository packages installed by slinstaller.

### Invariants
- **xbps-src compatible.** Templates follow void-packages conventions and its
  `Manual.md`.
- **Small, concentrated rebrand delta.** Branding in base-files/GRUB/efibootmgr
  and similar; no blanket `void` → `sunlight` renames.
- **Verified sources.** Every `distfiles` has a correct `checksum`.
- **Mergeable with upstream.** Keep the diff small so `void-packages` syncs are
  routine, not conflict storms.

### Reference sources
- **void-packages**: <https://github.com/void-linux/void-packages> — the fork
  base. Its `Manual.md` is the authoritative packaging reference; existing
  `srcpkgs/*` templates are the idiom to match.
- **slinstaller / slmanifests**: the installer that consumes these packages, and
  the tree that wires the projects together.

### Commit style
- **Bundle, don't over-split.** One commit per session of work. Commit
  messages: `area: short summary` + a paragraph on *why*, not *what* (the diff
  already shows what).
