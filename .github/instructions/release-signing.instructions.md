---
applyTo: "tools/ci-publish.sh,tools/ci-build.sh,tools/ci-lib.sh"
---

Only the trusted publish job may hold the package-signing key or a token that can modify releases. The separate attestation job may have OIDC and attestation-write permissions, but receives only accepted, published package files and no package-signing key. Treat build artifacts as untrusted data and validate them before signing. Never copy credentials into build steps, logs, artifacts, or agent contexts. During a review, do not execute publishing or signing workflows unless the user explicitly requests publication.
