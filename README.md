# proton-drive: a Claude skill for your Proton Drive

Lets Claude list, search, read, edit, create, move and delete files in your personal Proton Drive, with the safety rules enforced by a script instead of left to the model's judgement.

> **Unofficial.** Not affiliated with or endorsed by Proton AG. Proton Drive has no public API for this; see "How it works" for what is used instead.

## Two ways to reach your files

| | `local` | `rclone` (cloud) |
|---|---|---|
| Where it runs | your PC, with the Proton Drive desktop app signed in | anywhere: Claude app on a phone, cloud sessions |
| How | the folder the app keeps synced | rclone's community `protondrive` backend (beta) |
| Credentials | none, the app is already signed in | Proton session tokens in the environment: **use a dedicated secondary account** |
| Online-only files | detected without downloading (Windows, macOS) | every read is a download, large files are gated |

## Safety, enforced in code
- One configurable **root folder**; `..`, absolute paths elsewhere and symlinks leading out are refused; optional excluded patterns.
- **Backups before every overwrite, move-over-existing and delete**, stored outside the root (outside the synced folder, or in a separate folder of the same Proton account for cloud mode), restorable with one command.
- **Explicit confirmation** (`--confirmed`) for overwrite, move, delete, restore and prune; the skill tells Claude to pass it only after your yes.
- **Large and online-only files** are never downloaded without asking.
- Edits happen on a **work copy** and are written back once, then verified.
- Optional `read_only` mode.

## Install

**As a Claude Code plugin (recommended)**, from this repository's own marketplace:
```bash
claude plugin marketplace add FilippoBoi/proton-drive-skill
claude plugin install proton-drive@proton-drive-marketplace
```
or in one step on Claude Code 2.1.275 or later: `/plugin install proton-drive --marketplace FilippoBoi/proton-drive-skill`.

**Or copy the skill by hand.**

**On your PC (synced folder):**
```bash
mkdir -p ~/.claude/skills && cp -r skills/proton-drive ~/.claude/skills/
```
On Windows copy the folder to `%USERPROFILE%\.claude\skills\proton-drive`. Then ask Claude about your Proton Drive; on first use it asks which folder to use as root.

**Phone / cloud sessions:** read [cloud-setup.md](skills/proton-drive/references/cloud-setup.md) first (it involves storing login material in a cloud environment). Cloud sessions load skills from the repository attached to the session (`.claude/skills/`) or from skills uploaded to your account, so copy `skills/proton-drive` into the `.claude/skills/` folder of a repository you attach, or upload the packaged skill:
```bash
cd skills && zip -r ../proton-drive.skill proton-drive -x '*/__pycache__/*'
```

## How it works
Proton publishes no stable public API; its Drive SDK is still a preview not meant for third parties. So the skill uses the desktop app's synced folder (`local`) or rclone's `protondrive` backend (`rclone`), which is built from reverse-engineered behaviour and may break when Proton updates its apps. All operations go through [`scripts/pd.py`](skills/proton-drive/scripts/pd.py) (Python 3.9+, standard library only, about 850 lines): read it before trusting it with your files.

## Development
```bash
python -m unittest discover -s tests -v
```
Local-backend tests always run. Cloud-backend tests use rclone's `alias` remote on a temp folder (no Proton account needed) and run when rclone >= 1.66 is installed (`python skills/proton-drive/scripts/install_rclone.py`). CI runs on Linux, macOS and Windows.

## Known limits
- Sees only the synced folder (local) or the configured root (cloud); no sharing links, permissions or cloud-side version history.
- Cloud mode: tokens can expire and an ephemeral container cannot keep refreshed ones, so you may need to re-export your login now and then.
- The cloud mode has not been tested against a live Proton account by the author of this repository's first version; run `pd.py doctor` and report what you see.

## Security and privacy
See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md). License: [MIT](LICENSE).
