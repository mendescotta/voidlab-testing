#!/usr/bin/env bash
# Daily check for .github/workflows/watchdog.yml: a schedule that silently stops looks the same as "no
# updates". Opens (or edits) one `ci-watchdog` issue when auto-update has no successful scheduled run in
# the last 36 h or overlay-report none in the last 9 days, and closes it when both are healthy again.
set -euo pipefail

export GH_REPO=${GH_REPO:-${GITHUB_REPOSITORY:-}}
now=$(date -u -d "${WATCHDOG_NOW:-now}" +%s)

problems=""
check() { # workflow file, max age in hours
	local wf=$1 max=$2 latest first created conclusion last_success ts age
	if ! latest=$(gh run list --workflow "$wf.yml" --event schedule --limit 100 --json createdAt,conclusion,status \
		--jq '[.[] | select(.status == "completed")] as $runs | if ($runs | length) == 0 then "" else [($runs[0].createdAt // "-"), ($runs[0].conclusion // "-"), ([$runs[] | select(.conclusion == "success")][0].createdAt // "-")] | @tsv end'); then
		echo "ci-watchdog: cannot query scheduled runs for $wf" >&2
		return 1
	fi
	if [ -n "$latest" ]; then
		IFS=$'\t' read -r created conclusion last_success <<<"$latest"
		if [ "$last_success" != - ]; then
			if ! ts=$(date -u -d "$last_success" +%s); then
				echo "ci-watchdog: invalid successful-run timestamp for $wf: $last_success" >&2
				return 1
			fi
			age=$(((now - ts) / 3600))
			[ "$age" -gt "$max" ] || return 0
		fi
		if [ "$created" != - ] && [ "$conclusion" != success ]; then
			problems+="- \`$wf\`: latest completed scheduled run concluded $conclusion ($created); no success within ${max}h"$'\n'
		elif [ "$last_success" != - ]; then
			problems+="- \`$wf\`: last successful scheduled run $last_success (${age}h ago, limit ${max}h)"$'\n'
		fi
		return 0
	fi

	# In-progress runs are ignored; a workflow younger than its limit may not have completed a scheduled run yet.
	if ! first=$(gh run list --workflow "$wf.yml" --limit 500 --json createdAt --jq '.[-1].createdAt // empty'); then
		echo "ci-watchdog: cannot query run history for $wf" >&2
		return 1
	fi
	if [ -z "$first" ]; then
		problems+="- \`$wf\`: no successful scheduled run found"$'\n'
		return 0
	fi
	if ! ts=$(date -u -d "$first" +%s); then
		echo "ci-watchdog: invalid first-run timestamp for $wf: $first" >&2
		return 1
	fi
	if [ $(((now - ts) / 3600)) -gt "$max" ]; then
		problems+="- \`$wf\`: no successful scheduled run found (first run $first)"$'\n'
	fi
}

check auto-update 36 || exit $?
check overlay-report 216 || exit $?

if ! n=$(gh issue list --state open --label ci-watchdog --json number --jq '.[0].number // empty'); then
	echo "ci-watchdog: cannot query the open watchdog issue" >&2
	exit 1
fi
if [ -n "$problems" ]; then
	body=$(printf 'Scheduled workflows are not running as expected:\n\n%s\nCheck the Actions tab (a disabled schedule, an expired token or a failing job all look like this). This issue closes itself when both are healthy.\n' "$problems")
	if ! gh label create ci-watchdog --color D93F0B >/dev/null 2>&1; then
		labels=$(gh label list --json name --jq '.[].name') || {
			echo "ci-watchdog: cannot verify the ci-watchdog label" >&2
			exit 1
		}
		grep -Fxq ci-watchdog <<<"$labels" || {
			echo "ci-watchdog: cannot create the ci-watchdog label" >&2
			exit 1
		}
	fi
	if [ -n "$n" ]; then
		gh issue edit "$n" --body "$body"
	else
		gh issue create --title "CI watchdog: scheduled workflow not running" --label ci-watchdog --body "$body"
	fi
elif [ -n "$n" ]; then
	gh issue close "$n" --comment "Both scheduled workflows are healthy again."
fi
exit 0
