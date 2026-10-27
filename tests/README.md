# Repository bootstrap regression checks

Run `bash tests/test-bootstrap.sh` (or `python3 tests/test-bootstrap.py`). The
test executes each of the four pre-checkout bootstrap blocks with mocked
package commands and temporary repository configuration. It covers a healthy
CI mirror, failure at each install stage, and failure of both mirrors. No
network or root access is needed. The shell entry point is discovered by
`tools/ci-check.sh`.
