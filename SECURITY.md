# Security Policy

## Supported versions

Security fixes are applied to the latest published MoviePoster release and the current `main` branch.

## Reporting a vulnerability

Please do not open a public Issue for vulnerabilities that could expose credentials, local file paths, databases, media-library information or enable code execution.

Report the issue privately to the maintainer through the contact method on the maintainer's GitHub profile. Include reproduction steps, affected version and impact. Do not include real API keys, passwords, private media data or other secrets in the report.

## Secret handling

MoviePoster public source and release artifacts must not contain:

- `config.json` with real user settings
- TMDB or other API keys/tokens
- SQLite databases and undo logs
- cached posters/backdrops or browser/session data
- local/NAS paths that identify a maintainer's private environment
- media files or private library metadata

If a secret is accidentally committed, rotate/revoke it first and then remove it from Git history before publishing.
