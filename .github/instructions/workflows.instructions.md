---
applyTo: ".github/workflows/**,.github/actions/**"
---

Treat pull request inputs as untrusted. Keep PR workflows read-only, with no secrets, privileged builds, or publishing. Preserve the separation between untrusted build jobs and trusted publishing jobs. Run actionlint on workflow edits.
