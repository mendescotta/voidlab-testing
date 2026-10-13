# voidlab-testing

This repository is an overlay of Void Linux package templates and a signed
binary repository. It is not a fork of `void-packages`. `srcpkgs/` contains the
templates we carry; `common/` contains overlay changes to upstream packaging;
`./voidlab` manages the upstream checkout, builds, tests, updates and publishing.
The generated `.upstream/`, `hostdir/`, `masterdir/` and `repo/` directories are
not source files. Start with [README.md](README.md) and [docs/ci.md](docs/ci.md).

Void's `Manual.md`, `srcpkgs/`, `common/` and `xbps-src` define how packaging
works. After `./voidlab sync`, consult `.upstream/Manual.md` and comparable
upstream templates before changing ours. Templates are Bash scripts processed
by `xbps-src`.

## Working on a template

- Check `git status` first. Compare the overlay template with its upstream
  counterpart and keep intentional differences small. Some templates are new;
  others split packages or rebuild against newer libraries. See
  `tools/keep-overlay.list` for deliberate same-version overrides.
- Prefer a suitable `build_style` and Void's packaging helpers over custom
  `do_*` functions. Add dependencies for demonstrated build or runtime needs;
  distinguish `hostmakedepends`, `makedepends`, `checkdepends` and `depends`.
- Use `distfiles` and matching `checksum` values. For a new upstream release,
  change `version`, reset `revision=1` and refresh the checksum. For a change
  to the produced package at the same version, increment `revision`.
- Follow upstream field order and `xlint`. Use `${version}` in URLs where it
  applies. Avoid `wrksrc` when the normal extraction logic works. Give new or
  changed patches a `Why:`, `Upstream:` and `Drop when:` header, or a Git patch
  `Subject:` with an explanatory body. Do not rewrite copied upstream patches
  just to change their formatting.
- Give new subpackages the appropriate `srcpkgs/<name>` symlink. Check
  `common/shlibs` when library SONAMEs change. Avoid unrelated template edits.

## Local workflow

```sh
./voidlab sync                 # refresh the generated upstream checkout
xlint srcpkgs/<pkg>/template  # lint an overlay template
./voidlab build <pkg>          # apply overlay, build and index the package
./voidlab test <pkg>           # check package version, dependencies and SONAMEs
./voidlab update --check      # inspect available updates
./voidlab tiers               # inspect automatic update policy
./voidlab redundant           # find templates now covered by Void
```

`./voidlab sync` resets the generated `.upstream/` checkout. `./voidlab build`
reapplies the overlay before building. Do not run two `xbps-src` builds at once.
For changes to CI scripts, run the relevant `tests/test-*.sh` scripts. The PR
gate in `tools/ci-check.sh` lints changed templates and patches and runs the
test suite. Use a clean build and installation or VM smoke test when behavior
at runtime changes. [EXAMPLES.md](EXAMPLES.md) shows concrete review cases.

## Repository boundaries

- `tools/update-tiers` controls which templates CI updates automatically.
  Libraries and session components often require coordinated manual updates.
- `tools/never-publish` excludes packages such as NVIDIA from the public repo.
  Do not publish those packages. Ask before `./voidlab publish`, creating a
  release, force-pushing or rewriting history.
- Use a short commit subject without a body or trailer, following the workspace
  convention. Keep upstream comparisons and verification results in the work
  report.

The general advice to check assumptions and keep changes focused was adapted
from [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills)
(MIT). Repository facts and commands above are specific to voidlab-testing.
