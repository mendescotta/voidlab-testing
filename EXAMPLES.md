# Template review examples

These examples expand on [CLAUDE.md](CLAUDE.md). Check the current
`.upstream/Manual.md` and comparable Void templates for details.

## New package

For a new CMake project, first inspect its release archive and build files.
Use `build_style=cmake` if its defaults fit, then add only the host tools and
target libraries the build needs. Set `distfiles` and verify its `checksum`.
Add a `-devel` subpackage when the install actually includes headers or link
symlinks, and add the corresponding `srcpkgs/<name>` symlink. Run `xlint`,
`./voidlab build <pkg>` and `./voidlab test <pkg>`.

## Version update versus rebuild

For a new upstream release, change `version`, reset `revision=1`, and update
the source checksum. For a packaging change at the same upstream version,
increment `revision` if the produced package changes. Confirm that a local
release archive matches the template checksum before reusing it.

## Overlay change to a Void template

Compare the template and its patches with `.upstream/srcpkgs/<pkg>/`. Keep the
copied files identical where possible. If the package must remain in the
overlay at the same version, record its reason in `tools/keep-overlay.list`.
Put a new source fix in `srcpkgs/<pkg>/patches/`, explain why it is needed and
when it can be dropped, then build and test the affected package. A SONAME
change also requires checking `common/shlibs` and reverse dependencies.

## Refreshing upstream

`./voidlab sync` refreshes the generated `.upstream/` checkout and clears
overlay copies in that checkout. The source templates in this repository stay
intact. `./voidlab build <pkg>` reapplies them. Review `./voidlab redundant`
after a refresh to see whether Void now provides an overlay package.
