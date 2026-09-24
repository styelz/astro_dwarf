---
description: Bump the version, commit, and push so GitHub Actions publishes a release
---

The user's message is permission to commit and push this release. Do that in this turn.

The lines they typed under `/version-bump` are the release highlights. Keep their wording. Turn each line into a markdown bullet if it is not one already. Write those bullets, and nothing else, to `packaging/release_highlights.md`. If they gave no lines, write that file empty so the previous release's notes are not reused.

Choose the version from the diff since the latest `v*` tag:

- **patch** for fixes, polish, and small behavior
- **minor** for a new thing a person can start from the HUD
- **major** only when saved sessions, settings, or device commands break for someone already using the app

When the mix is unclear, use patch. Read `VERSION`. If it already equals the latest tag, run `python packaging/bump_version.py --bump patch|minor|major`. If `VERSION` is already newer than that tag, keep it unless the changes clearly deserve a higher part.

Commit every source change for this release, including `VERSION`, `packaging/release_highlights.md`, and this command when it is untracked. Do not commit `data/`, logs, `config.py`, `config.ini`, credentials, tokens, location, `__pycache__`, `.venv`, `build/`, or `dist/`.

Commit message, on PowerShell:

```powershell
git commit -m @"
Release X.Y.Z

- their first line

"@
```

Do not put `[skip ci]` in the message. A push to `main` that changes `VERSION` is what starts the installer workflow. If `HEAD` is not `main`, stop and say so. Push with `git push origin HEAD`.

Then tell the user the version, the highlights that will sit above the screenshot, and that the release starts when the workflow finishes.
