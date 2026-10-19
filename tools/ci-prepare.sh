#!/bin/sh
# Finish preparing a ghcr.io/void-linux/void-glibc-full container after checkout. The workflow configures
# the CI mirror, updates the system, and installs git before checkout; xbps-src refuses to build as root.
set -eu

retry() {
	n=0
	until "$@"; do
		n=$((n + 1))
		[ "$n" -lt 3 ] || return 1
		echo "retrying ($n/3): $*" >&2
		sleep 5
	done
}

retry xbps-install -y sudo bash curl github-cli xtools openssl perl

id builder >/dev/null 2>&1 || useradd -G xbuilder -m builder
# the checkout is owned by another uid than the one running git
git config --system --add safe.directory '*'
