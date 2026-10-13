# EXAMPLES.md

Concrete examples for each of the four principles in [CLAUDE.md](CLAUDE.md),
grounded in real scenarios (`xbps-src` templates, upstream
syncs). Snippets use the template shell format and diffs.

> Derived from [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)
> (MIT). Examples rewritten for xbps-src packaging
---

## 1. Think Before Coding

### Example 1 — Ambiguous Packaging Request

**User request:** "Add a package for `foo`."

**What LLMs often do (wrong assumption):**

```sh
# srcpkgs/foo/template
pkgname=foo
version=1.0
revision=1
do_build() {
    make
}
do_install() {
    make install
}
```

**Problem:** several decisions are made silently, and each is a real choice:

- **What build system?** If `foo` uses autotools/cmake/meson, a `build_style`
  handles configure/build/install correctly — a bare `make` usually won't.
- **Dependency kinds:** what goes in `depends` (runtime) vs `makedepends`
  (build) vs `hostmakedepends` (e.g. `pkg-config`)?
- **Source + checksum:** there's no `distfiles`/`checksum` — the package fetches
  nothing.
- **Subpackages:** does `foo` ship headers (`foo-devel`)?

**What should happen (surface the choice):**

> Before I write the template:
>
> 1. What build system does `foo` use? (I'd set `build_style` accordingly,
>    e.g. `gnu-configure` / `cmake` / `meson`.)
> 2. Runtime vs build dependencies?
> 3. Upstream tarball URL + checksum?
> 4. Any `-devel`/`-doc` subpackage needed?
>
> I'll model it on an existing `srcpkgs/<similar>/template`.

### Example 2 — Update: Version vs Revision

**User request:** "Bump `foo`."

**What LLMs often do (pick silently):**

```diff
-revision=1
+revision=2
```

(Bumps the packaging revision when the user meant a new upstream version — or
vice versa.)

**What should happen:**

> "Bump" is ambiguous:
>
> 1. **New upstream release** → change `version`, reset `revision=1`, and update
>    `checksum` for the new tarball.
> 2. **Packaging-only rebuild** (patch, dep fix) → bump `revision` only.
>
> Which one? If it's a new version, I'll also re-fetch and update the checksum —
> never carry an old checksum forward.

---

## 2. Simplicity First

### Example 1 — Reinventing build_style

**User request:** "Package `bar`, which uses CMake."

**What LLMs often do (overengineered):**

```sh
do_configure() {
    mkdir build && cd build
    cmake -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_BUILD_TYPE=Release ..
}
do_build() {
    cd build && make ${makejobs}
}
do_install() {
    cd build && make DESTDIR=${DESTDIR} install
}
```

**Problem:** `xbps-src` has `build_style=cmake` that does exactly this, with the
right flags and out-of-tree build, consistently across the whole tree.

**What should happen (minimum template):**

```sh
build_style=cmake
# configure_args only if bar needs something non-default
```

Let the build_style do its job. Hand-write `do_*` only when no style fits.

### Example 2 — Speculative Subpackages

**User request:** "Package the `baz` library."

**What LLMs often do (feature creep):**

```sh
baz-devel_package() { ... }
baz-doc_package()   { ... }
baz-static_package(){ ... }
baz-dbg_package()   { ... }   # dbg is automatic in xbps-src
```

**Problem:** `-dbg` is produced automatically; `-doc`/`-static` may not apply.
Inventing subpackages that have nothing to put in them fails the build or ships
empties.

**What should happen:**

Ship the library, plus a `-devel` subpackage **only if** headers/`.so` symlinks
are actually installed:

```sh
baz-devel_package() {
    depends="${sourcepkg}>=${version}_${revision}"
    short_desc+=" - development files"
    pkg_install() {
        vmove usr/include
        vmove "usr/lib/*.so"
    }
}
```

Add `-doc`/`-static` only when there's content for them.

---

## 3. Surgical Changes

### Example 1 — Drive-by Reformatting

**User request:** "Update `qux` to 2.0."

**What LLMs often do (too much):**

```diff
-pkgname=qux
-version=1.4
-revision=3
-build_style=gnu-configure
-short_desc="A qux tool"
-maintainer="x <x@y>"
-license="MIT"
-homepage="https://example.org"
-distfiles="https://example.org/qux-${version}.tar.gz"
-checksum=abc123...
+pkgname=qux
+version=2.0
+revision=1
+build_style=gnu-configure
+configure_args="--enable-everything"   # not requested
+short_desc="A qux tool (the best one)"  # reworded
+maintainer="x <x@y>"
+license="MIT"
+homepage="https://example.org"
+distfiles="https://example.org/qux-${version}.tar.gz"
+checksum=def456...
+# ...fields reordered
```

**Problems:**
- Added `configure_args` nobody asked for.
- Reworded `short_desc` and reordered fields — noise in the diff.
- The real change is three lines.

**What should happen (surgical):**

```diff
-version=1.4
-revision=3
+version=2.0
+revision=1
-checksum=abc123...
+checksum=def456...
```

Version, revision reset to 1, new checksum. Nothing else.

### Example 2 — Rebrand Blast Radius

**User request:** "Rebrand the distro name in base-files."

**What LLMs often do (mass rename):**

```sh
# Runs across the whole tree:
grep -rl void srcpkgs/ | xargs sed -i 's/void/sunlight/g'
```

**Problem:** this rewrites package names (`void-` packages), upstream URLs,
mirror hostnames, kernel/module references, and `vlogo`-type asset names — most
of which **must** match upstream. It breaks builds and turns every future
void-packages sync into a conflict storm.

**What should happen:**

Change only the intended branding string in the intended file:

```diff
 # srcpkgs/base-files/files/os-release
-NAME="Void"
-PRETTY_NAME="Void Linux"
+NAME="Voidlab"
+PRETTY_NAME="Sunlight Linux"
-HOME_URL="https://voidlinux.org/"
+HOME_URL="https://voidlinux.org/"
```

The rebrand stays concentrated; package names and upstream references are
untouched.

---

## 4. Goal-Driven Execution

### Example 1 — Reproduce, Then Fix

**User request:** "`foo` fails to build."

**What LLMs often do (fix without reproducing):**

```diff
+hostmakedepends="pkg-config automake libtool gettext flex bison"
```

(Throws a pile of build deps at it on a hunch.)

**What should happen (reproduce in a clean masterdir):**

```
Plan:
1. Reproduce: ./xbps-src pkg foo  (clean masterdir).
   Verify: capture the actual error (e.g. "configure: error: pkg-config not
   found" or a missing header).
2. Map the error to one missing piece (a hostmakedepends like pkg-config, or a
   makedepends like libfoo-devel).
   Verify: the error names exactly what's missing.
3. Add just that dependency.
   Verify: ./xbps-src pkg foo now builds; xlint clean.
```

Add the one dependency the build actually needs — not a grab-bag.

### Example 2 — Multi-Step Upstream Sync

**User request:** "Sync slpkgs with the latest void-packages."

**What LLMs often do (all at once):**

`git merge upstream/master`, blindly accept all conflict resolutions, and push —
without rebuilding anything or checking the rebrand survived.

**What should happen (incremental):**

```
Plan:
1. Add upstream remote and fetch:
   git remote add upstream https://github.com/void-linux/void-packages.git
   git fetch upstream
   Verify: upstream/master is available.
2. Merge; resolve conflicts only in the custom templates ahead of void's, take upstream elsewhere.
   Verify: git diff shows the rebrand intact and a small delta.
3. Rebuild the packages touched by the merge.
   Verify: ./xbps-src pkg <changed> succeeds; xlint clean.
4. Smoke-test the base-system packages (ideally in a VM).
   Verify: os-release/branding correct; system boots.
```

Each step is checkable; the concentrated rebrand is what makes step 2 tractable.

---

## Anti-patterns Summary

| Principle | Anti-pattern | Fix |
|---|---|---|
| Think Before Coding | Bare `do_build(){ make }` for "add package foo" | Ask build system + deps + source/checksum; use a `build_style` |
| Simplicity First | Hand-written cmake `do_*` steps | `build_style=cmake` |
| Goal-Driven | Pile of `hostmakedepends` on a hunch for a build failure | Reproduce in a clean masterdir; add the one missing dep |

## Key Insight

The "overcomplicated" examples aren't obviously wrong — explicit build steps,
extra subpackages, and broad renames all look thorough. The problem is **timing
and blast radius**: in a packaging fork, premature breadth and incidental edits
either break the build, ship empty/wrong packages, or — worst for a fork —
**inflate the delta from upstream** so every void-packages sync becomes a
conflict storm.

- Match upstream void-packages idiom; the smaller the diff, the easier the
  merges.
- Keep the rebrand concentrated; never mass-rename `void` → `voidlab`.
- The real test is `./xbps-src pkg` in a clean masterdir, plus `xlint`.

**Good slpkgs changes are the smallest template/rebrand delta that solves the
need while staying buildable and mergeable with upstream void-packages.**
