# omaforge

A World of Warcraft addon manager for [Omarchy](https://omarchy.org). It finds
every WoW client in your Wine prefixes, shows what each one has installed, and
installs and updates addons from CurseForge, WoWInterface and GitHub. It
follows your Omarchy theme and has a CLI for timers and keybindings.

## What it does

- **Finds your games.** Scans Lutris, Steam/Proton, Bottles, Heroic and
  `~/.wine` prefixes (and any folder you add) for `World of Warcraft`, then
  every `_*_` client folder inside: Retail, PTR, beta, Classic Era,
  progression Classic, anniversary realms and **World of Warcraft: Forever**.
- **Knows what's installed, even if omaforge didn't install it.**
  - CurseForge folder fingerprints identify the exact file.
  - TOC headers (`X-Curse-Project-ID`, `X-WoWI-ID`, `X-Wago-ID`) link addons to their sources.
  - WoWInterface folder lists and `X-Website` GitHub links catch the rest.
  - Multi-folder addons (DBM, BigWigs, ElvUI) show as one entry.
  - Anything unmatched is listed as *unknown*, never hidden.
- **Updates safely.** Downloads are extracted next to `AddOns` and swapped in
  with atomic renames; a failure rolls back. Folders an update no longer
  ships are removed. `WTF` is backed up before every bulk update, and backups
  can be restored.
- **Per-addon control.** Pin a version, ignore an addon, or follow its
  stable, beta or alpha channel.
- **Moves with you.** Export a client's addon list to JSON and import it on
  another machine or client.

## Sources

| Source | Needs | Notes |
|---|---|---|
| CurseForge | API key issued to omaforge | Search, install, update, fingerprint matching. Authors can opt out of third-party downloads; omaforge then says so and points to curseforge.com. |
| WoWInterface | nothing | Public MMOUI API. One release per addon (stable). |
| GitHub | nothing (token optional) | Releases built with the BigWigs packager; `release.json` picks the right zip per flavor. A token raises the rate limit from 60 to 5,000 requests an hour. |
| Wago Addons | API key | Stubbed until access is granted. |

omaforge never scrapes websites and never uses another app's API keys.

## Game versions

Clients are identified from their files: `.flavor.info` gives the product
(`wow`, `wow_classic_era`, `wow_classic_beta`, ...), and `.build.info` gives its
version. One table, [`omaforge/core/flavors.toml`](omaforge/core/flavors.toml),
maps them to a game, the TOC suffixes that game reads, and the packager and
CurseForge flavors to install. To add a branch without a code change, put rules
in `~/.config/omaforge/flavors.toml`; they are tried before the built-in ones.

**Forever**:

- The beta client is `_classic_beta_`, product `wow_classic_beta`, version
  1.60.x (interface 16001).
- The BigWigs packager builds for it as flavor `forever` (alias `camelot`),
  with `_Camelot` TOC files.
- CurseForge lists it as game version type 88568.
- Whether the client also reads `_Classic` TOCs has not been confirmed.
- The live client's product id is unknown, so any client in the 1.60 range is
  treated as Forever. That rule is marked unverified.

## Install

On Arch or Omarchy, download the package from the
[latest release](https://github.com/ninepointlabs/omaforge/releases/latest) and:

```sh
sudo pacman -U omaforge-*-any.pkg.tar.zst
omaforge setup omarchy                                 # "WoW Addons" in the Omarchy menu
omaforge setup omarchy --keybind "SUPER + SHIFT + Z"   # optional keybinding
```

Release packages include omaforge's CurseForge API key, so CurseForge works out
of the box. Building from source (`cd packaging && makepkg -si`) gives a
package without it; add your own key under **Settings** or in
`~/.config/omaforge/config.toml`:

```toml
[providers.curseforge]
api_key = "..."
```

The launcher entry comes from the desktop file. `omaforge setup omarchy --remove`
undoes the menu entry and keybinding, which live between marker comments in
`~/.config/omarchy/extensions/omarchy-menu.jsonc` and `~/.config/hypr/bindings.lua`
(a backup is written first).

## Releasing

Bump `pkgver` in `packaging/PKGBUILD` and `version` in `pyproject.toml` /
`omaforge/__init__.py`, then push a `v<version>` tag. The Release workflow
builds the package in an Arch container, embeds the CurseForge key from the
`CURSEFORGE_API_KEY` repository secret (obfuscated; see
`omaforge/buildkey.py`), runs the tests and attaches the package to a GitHub
release. The key is never committed.

## Command line

```sh
omaforge                      # open the app
omaforge clients              # detected clients
omaforge list --check -c forever
omaforge search bigwigs -c retail
omaforge install curseforge:2382 github:DeadlyBossMods/DeadlyBossMods wowi:11190
omaforge update --all --notify   # every client; WTF backed up first
omaforge pin|unpin|ignore|unignore <addon>
omaforge channel <addon> beta
omaforge uninstall <addon>
omaforge backup [create|list|restore <id>]
omaforge export retail.json && omaforge import retail.json -c forever
omaforge setup omarchy [--keybind KEYS] [--remove]
```

Every command takes `--json` and `--offline`. Addons can be named by key,
folder or title.

Daily updates with a notification:

```sh
systemctl --user enable --now omaforge-update.timer
```

## Files

| Path | What |
|---|---|
| `~/.config/omaforge/config.toml` | settings and API keys (mode 0600) |
| `~/.config/omaforge/flavors.toml` | optional extra flavor rules |
| `~/.local/share/omaforge/state.json` | what omaforge installed; pins, ignores, channels |
| `~/.local/share/omaforge/backups/` | WTF snapshots per client |
| `~/.cache/omaforge/` | cached API responses |

## Development

```sh
uv venv --system-site-packages --python /usr/bin/python3 .venv
uv pip install --python .venv/bin/python pytest
.venv/bin/python -m pytest -q
.venv/bin/python -m omaforge
```

The core (`omaforge/core`) has no Qt dependency; the UI (`omaforge/ui`) is
PySide6 + Qt Quick and talks to the core only through `Manager`.
