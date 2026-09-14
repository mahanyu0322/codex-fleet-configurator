# Security

This application edits local Codex settings. It does not call model APIs, collect telemetry, upload files, or store API credentials of its own.

Backups can contain sensitive values already present in the original configuration. Keep them local. New backup directories use owner-only permissions on macOS/POSIX; Windows uses the user's existing directory ACLs. Do not attach raw configuration or backup files to a public issue.

Report vulnerabilities through this repository's GitHub **Security → Report a vulnerability** feature. Include a minimal reproduction with invented values and remove credentials, usernames, local paths and organization details. For ordinary bugs, use Issues.

Initial binaries are not signed with Windows Authenticode or notarized with Apple Developer ID. Verify the SHA-256 checksum from the same GitHub release and review the source when deciding whether to run a download. Do not disable system-wide security controls.
