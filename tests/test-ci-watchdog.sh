#!/usr/bin/env bash
# tools/ci-watchdog.sh: opens one issue when a scheduled workflow has not succeeded recently, closes it
# when healthy. Fake gh driven by files in $W.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); . "$HERE/lib.sh"
WD=$HERE/../tools/ci-watchdog.sh
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT

cat > "$W/gh" <<'X'
#!/usr/bin/env bash
echo "gh $*" >> "$W/calls"
case "$1 $2" in
"run list")
	wf= ev=
	while [ $# -gt 0 ]; do
		case $1 in
		--workflow) wf=$2; shift 2 ;;
		--event) ev=$2; shift 2 ;;
		*) shift ;;
		esac
	done
	[ ! -f "$W/fail-run-list" ] && [ ! -f "$W/fail-run-list-${wf%.yml}" ] || exit 1
	if [ "$ev" = schedule ]; then
		f=$W/last-${wf%.yml}
		success=$(cat "$W/success-${wf%.yml}" 2>/dev/null || true)
		if [ -f "$f" ] && [ "$(cat "$W/status-${wf%.yml}" 2>/dev/null || echo completed)" = completed ]; then
			read -r created < "$f"
			conclusion=$(cat "$W/conclusion-${wf%.yml}" 2>/dev/null || echo success)
			[ -n "$success" ] || [ "$conclusion" != success ] || success=$created
			printf '%s|%s|%s\n' "$created" "$conclusion" "$success"
		elif [ -n "$success" ]; then
			printf '||%s\n' "$success"
		fi
	else
		cat "$W/first-${wf%.yml}" 2>/dev/null || true
	fi ;;
"issue list")
	[ ! -f "$W/fail-issue-list" ] || exit 1
	cat "$W/open-issue" 2>/dev/null || true ;;
"issue create"|"issue edit")
	while [ $# -gt 0 ]; do [ "$1" = --body ] && printf '%s' "$2" > "$W/body"; shift; done ;;
*) ;;
esac
X
chmod +x "$W/gh"
export W
export PATH=$W:$PATH WATCHDOG_NOW=2026-10-09T12:00:00Z GH_REPO=o/r

setup() { rm -f "$W"/last-* "$W"/first-* "$W"/success-* "$W"/conclusion-* "$W"/status-* "$W"/open-issue "$W"/body "$W"/fail-* "$W"/calls; : > "$W/calls"; }
run() { bash "$WD" 2>&1; }

# 1. both fresh, no open issue -> nothing created
setup
echo 2026-10-09T04:30:00Z > "$W/last-auto-update"
echo 2026-10-06T05:00:00Z > "$W/last-overlay-report"
out=$(run) && rc=0 || rc=$?
assert_eq "healthy exits 0" "$rc" "0"
assert_eq "healthy creates no issue" "$(grep -c 'issue create' "$W/calls" || true)" "0"

# 1b. A failure is reported only when no recent successful run exists; in-progress runs do not page.
setup
echo 2026-10-09T04:30:00Z > "$W/last-auto-update"
echo failure > "$W/conclusion-auto-update"
echo 2026-10-06T05:00:00Z > "$W/last-overlay-report"
out=$(run) && rc=0 || rc=$?
assert_eq "failed scheduled run still exits successfully after reporting" "$rc" "0"
assert_grep "failed scheduled run is identified in the issue" 'latest completed scheduled run concluded failure' "$W/body"
setup
echo 2026-10-09T11:30:00Z > "$W/last-auto-update"
echo queued > "$W/status-auto-update"
echo 2026-10-09T04:30:00Z > "$W/success-auto-update"
echo 2026-10-06T05:00:00Z > "$W/last-overlay-report"
out=$(run) && rc=0 || rc=$?
assert_eq "in-progress run does not page when a recent success exists" "$rc" "0"
assert_eq "in-progress run does not create an issue" "$(grep -c 'issue create' "$W/calls" || true)" "0"
setup
echo 2026-10-09T11:30:00Z > "$W/last-auto-update"
echo failure > "$W/conclusion-auto-update"
echo 2026-10-09T04:30:00Z > "$W/success-auto-update"
echo 2026-10-06T05:00:00Z > "$W/last-overlay-report"
out=$(run) && rc=0 || rc=$?
assert_eq "transient failure is not reported while recent success is in window" "$rc" "0"
assert_eq "transient failure does not create an issue" "$(grep -c 'issue create' "$W/calls" || true)" "0"

# 2. auto-update stale (>36h) -> issue created, names the workflow
setup
echo 2026-10-07T04:30:00Z > "$W/last-auto-update"
echo 2026-10-06T05:00:00Z > "$W/last-overlay-report"
out=$(run) && rc=0 || rc=$?
assert_eq "stale exits 0 (the issue is the signal)" "$rc" "0"
assert_eq "stale creates one issue" "$(grep -c 'issue create' "$W/calls" || true)" "1"
assert_grep "issue mentions auto-update" 'auto-update' "$W/calls"

# 3. never ran -> counts as stale
setup
echo 2026-10-09T04:30:00Z > "$W/last-auto-update"
out=$(run) && rc=0 || rc=$?
assert_eq "never-run overlay-report creates an issue" "$(grep -c 'issue create' "$W/calls" || true)" "1"
assert_grep "issue mentions overlay-report" 'overlay-report' "$W/calls"

# 3b. a workflow too new to have had a scheduled run is not flagged; one older than the limit is
setup
echo 2026-10-09T04:30:00Z > "$W/last-auto-update"
echo 2026-10-07T10:00:00Z > "$W/first-overlay-report"
out=$(run) && rc=0 || rc=$?
assert_eq "a new workflow without a scheduled run yet is not flagged" "$(grep -c 'issue create' "$W/calls" || true)" "0"
setup
echo 2026-10-09T04:30:00Z > "$W/last-auto-update"
echo 2026-09-20T10:00:00Z > "$W/first-overlay-report"
out=$(run) && rc=0 || rc=$?
assert_eq "a schedule that never fired within the limit is flagged" "$(grep -c 'issue create' "$W/calls" || true)" "1"

# 4. already an open issue -> edited, not duplicated
setup
echo 2026-10-07T04:30:00Z > "$W/last-auto-update"
echo 2026-10-06T05:00:00Z > "$W/last-overlay-report"
echo 42 > "$W/open-issue"
out=$(run) && rc=0 || rc=$?
assert_eq "open issue is edited" "$(grep -c 'issue edit 42' "$W/calls" || true)" "1"
assert_eq "no duplicate issue" "$(grep -c 'issue create' "$W/calls" || true)" "0"

# 5. healthy again -> open issue closed
setup
echo 2026-10-09T04:30:00Z > "$W/last-auto-update"
echo 2026-10-06T05:00:00Z > "$W/last-overlay-report"
echo 42 > "$W/open-issue"
out=$(run) && rc=0 || rc=$?
assert_eq "healthy closes the open issue" "$(grep -c 'issue close 42' "$W/calls" || true)" "1"

# 6. API errors must fail the watchdog rather than looking like an unhealthy workflow.
setup
touch "$W/fail-run-list-auto-update"
echo 2026-09-30T04:30:00Z > "$W/last-overlay-report"
out=$(run) && rc=0 || rc=$?
assert_eq "run-list API error fails the watchdog" "$rc" "1"
assert_grep "run-list API error is explicit" 'cannot query scheduled runs for auto-update' <(echo "$out")
assert_grep "watchdog still checks overlay-report after auto-update API failure" 'run list --workflow overlay-report.yml' "$W/calls"
assert_grep "other workflow problems are reported despite an API error" 'last successful scheduled run' "$W/body"
assert_grep "API failure is reported distinctly" 'could not query scheduled runs' "$W/body"
assert_eq "API errors create one issue containing available results" "$(grep -c 'issue create' "$W/calls" || true)" "1"
setup
echo 2026-10-07T04:30:00Z > "$W/last-auto-update"
echo 2026-10-06T05:00:00Z > "$W/last-overlay-report"
touch "$W/fail-issue-list"
out=$(run) && rc=0 || rc=$?
assert_eq "issue-list API error fails the watchdog" "$rc" "1"
assert_grep "issue-list API error is explicit" 'cannot query the open watchdog issue' <(echo "$out")
assert_grep "issue-list API error logs the collected health problem" 'last successful scheduled run' <(echo "$out")
finish
