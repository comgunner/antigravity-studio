# Changelog

All notable changes to this project will be documented in this file.

## [1.0.2] - 2026-04-15

### Added
- **Environment Variable Support**: Integrated `python-dotenv` to load credentials from a local `.env` file instead of hardcoded values.
- **Quiet Mode**: Added `--quiet` flag to `chat` command to suppress headers and metadata for cleaner output when integrated with other scripts.
- **Robust Error Logging**: Added detailed OAuth error reporting to diagnose authentication failures (401/400 errors).

### Changed
- **Git History Cleaned**: Rebased repository history to consolidate all commits under a single verified contributor profile.
- **OAuth Infrastructure**: 
    - Switched redirect URIs from `127.0.0.1` to `localhost` to comply with modern Google security standards.
    - Simplified OAuth scopes to fix `403: restricted_client` errors.
    - Improved `client_secret` handling to support public/PKCE clients.
- **UI/UX Sanitization**: 
    - Refactored `antigravity_cli.py` and `coin_summary.py` to extract and display clean text instead of raw API JSON objects.
    - Added support for displaying "Thought" processes from newer Gemini models in a styled format (dim/italic).

### Fixed
- Fixed the `401: Unauthorized` error during token exchange by removing invalid client secret parameters for public clients.
- Fixed the `404: Not Found` error during `npm publish` by properly configuring the package scope and versioning.

---

## Rollback Procedures

If you encounter breaking issues with this version, follow these steps:

### 1. Revert Git History (Local)
If you need to return to a state before the history rewrite:
```bash
# This only works if you have not deleted the 'original' ref created by filter-repo
git reset --hard refs/original/refs/heads/main
```

### 2. Downgrade Dependencies
If the new `python-dotenv` causes issues:
```bash
pip uninstall python-dotenv
# Re-install original requirements
pip install -r requirements.txt
```

### 3. Restore Hardcoded Auth (Not Recommended)
If `.env` loading fails, you can manually re-insert your `client_id` in `antigravity_auth.py` within the `OAUTH_CONFIG` dictionary, although using the `.env` file is the preferred secure method.

### 4. Revert Version in package.json
To go back to version 1.0.1:
```bash
# Edit package.json and change "version": "1.0.2" to "1.0.1"
# Note: NPM will not allow you to re-publish 1.0.1 over an existing 1.0.1
```
