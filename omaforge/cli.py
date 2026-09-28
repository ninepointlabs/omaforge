"""Command-line interface: scripted updates, timers and everything the UI does."""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from omaforge import __version__
from omaforge.core.backup import BackupError
from omaforge.core.http import HttpError
from omaforge.core.install import InstallError
from omaforge.core.manager import Manager, ManagerError
from omaforge.core.models import CHANNELS
from omaforge.core.providers import ProviderError

PROVIDER_ALIASES = {"wowi": "wowinterface", "gh": "github", "cf": "curseforge"}


def _out(args, data, text: str) -> None:
    if args.json:
        print(json.dumps(data, indent=2, default=str))
    elif text:
        print(text)


def _table(rows: list[list[str]], header: list[str]) -> str:
    rows = [header] + rows
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(header))]
    lines = ["  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)


def _find_addon(m: Manager, client, ref: str):
    addons = m.installed(client)
    ref_l = ref.lower()
    for test in (lambda a: a.key.lower() == ref_l,
                 lambda a: a.main_folder.lower() == ref_l,
                 lambda a: a.name.lower() == ref_l,
                 lambda a: ref_l in (f.lower() for f in a.folders)):
        hits = [a for a in addons if test(a)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ManagerError(f"{ref!r} is ambiguous: {', '.join(a.key for a in hits)}")
    raise ManagerError(f"no installed addon {ref!r} in {client.label}")


def _parse_source(ref: str) -> tuple[str, str]:
    if ref.startswith(("https://github.com/", "github.com/")):
        return "github", ref.split("github.com/", 1)[1].strip("/")
    if ":" not in ref:
        raise ManagerError("give the addon as provider:id, e.g. wowinterface:5086 or github:BigWigsMods/BigWigs")
    provider, addon_id = ref.split(":", 1)
    return PROVIDER_ALIASES.get(provider, provider), addon_id


def _notify(summary: str, body: str) -> None:
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "omaforge", "-i", "omaforge", summary, body], check=False)


def cmd_clients(m: Manager, args) -> int:
    clients = m.clients()
    rows = [[c.key, c.label, c.version or "?", str(c.interface or "?"), c.product, str(c.path)] for c in clients]
    text = _table(rows, ["KEY", "CLIENT", "VERSION", "INTERFACE", "PRODUCT", "PATH"]) if rows else "no clients found"
    notes = [f"  {c.key}: {n}" for c in clients for n in c.notes]
    if notes and not args.json:
        text += "\n\nnotes:\n" + "\n".join(notes)
    _out(args, [c.to_dict() for c in clients], text)
    return 0


def _status(a) -> str:
    if a.ignored:
        return "ignored"
    if a.update_available:
        return f"-> {a.latest.version}" + (" (pinned)" if a.pinned else "")
    if a.update_error:
        return "?"
    if a.latest:
        return "up to date"
    return ""


def cmd_list(m: Manager, args) -> int:
    client = m.client(args.client)
    addons = m.installed(client)
    if args.check:
        m.check_updates(client, addons)
    rows = []
    for a in addons:
        source = f"{a.provider}:{a.source_id}" if a.provider else "unknown"
        flags = "".join(["P" if a.pinned else "", "I" if a.ignored else "", "!" if not a.compatible else "",
                         "x" if not a.loadable else ""])
        rows.append([a.name, a.version or "?", _status(a), source, a.match or "", a.channel, flags,
                     str(len(a.folders))])
    text = f"{client.label} ({client.version}) - {len(addons)} addons\n\n"
    text += _table(rows, ["NAME", "VERSION", "STATUS", "SOURCE", "MATCH", "CHANNEL", "FLAGS", "DIRS"]) if rows else "(none)"
    if rows:
        text += "\n\nFLAGS: P pinned, I ignored, ! may be out of date, x not loadable by this client"
    _out(args, {"client": client.to_dict(), "addons": [a.to_dict() for a in addons]}, text)
    return 0


def cmd_update(m: Manager, args) -> int:
    if args.all and not args.addons and not args.client:
        # Scripted `update --all`: every client that has addons.
        clients = [c for c in m.clients() if c.game is not None]
    else:
        clients = [m.client(args.client)]
    if not args.addons and not args.all:
        # `omaforge update` with nothing named behaves like `check`.
        return cmd_list(m, argparse.Namespace(**{**vars(args), "check": True}))

    rc, report, summary = 0, [], []
    for client in clients:
        keys = [_find_addon(m, client, ref).key for ref in args.addons] if args.addons else None
        backup = False if args.no_backup else None
        progress = None if args.json else (
            lambda a, c=client: print(f"{c.label}: updating {a.name} {a.version} -> {a.latest.version}", flush=True))
        res = m.update(client, keys, backup=backup, progress=progress)
        updated = [r for r in res.results if r.new]
        failed = [r for r in res.results if not r.ok]
        report.append({"client": client.key, **res.to_dict()})
        lines = []
        if res.backup:
            lines.append(f"backed up WTF to {res.backup['path']}")
        for r in res.results:
            if r.new:
                lines.append(f"updated  {r.name}: {r.old} -> {r.new}")
            elif r.error:
                lines.append(f"failed   {r.name}: {r.error}")
            elif args.addons:
                lines.append(f"skipped  {r.name}: {r.skipped}")
        if not updated and not failed:
            lines.append("everything is up to date")
        if not args.json:
            print(f"{client.label}:\n  " + "\n  ".join(lines) if len(clients) > 1 else "\n".join(lines))
        if failed:
            rc = 1
        if updated or failed:
            part = f"{client.label}: {len(updated)} updated"
            if failed:
                part += f", failed: {', '.join(r.name for r in failed)}"
            summary.append(part)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    if args.notify and summary:
        _notify("omaforge addon updates", "\n".join(summary))
    return rc


def cmd_search(m: Manager, args) -> int:
    client = m.client(args.client)
    providers = [PROVIDER_ALIASES.get(p, p) for p in args.provider] if args.provider else None
    results, errors = m.search(client, " ".join(args.query), providers)
    rows = [[f"{r.provider}:{r.id}", r.name, r.author, r.version, str(r.downloads)] for r in results[: args.limit]]
    text = _table(rows, ["SOURCE", "NAME", "AUTHOR", "VERSION", "DOWNLOADS"]) if rows else "no results"
    for p, e in errors.items():
        text += f"\n{p}: {e}"
    _out(args, {"results": [r.to_dict() for r in results], "errors": errors}, text)
    return 0


def cmd_install(m: Manager, args) -> int:
    client = m.client(args.client)
    rc = 0
    for ref in args.addons:
        provider, addon_id = _parse_source(ref)
        try:
            rec = m.install(client, provider, addon_id, args.channel, args.force)
            warn = " (flavor not verified for this client)" if rec["compat"] != "ok" else ""
            _out(args, rec, f"installed {rec['name']} {rec['version']} into {client.label}: {', '.join(rec['folders'])}{warn}")
        except (ManagerError, ProviderError, HttpError, InstallError) as e:
            print(f"{ref}: {e}", file=sys.stderr)
            rc = 1
    return rc


def cmd_uninstall(m: Manager, args) -> int:
    client = m.client(args.client)
    for ref in args.addons:
        a = _find_addon(m, client, ref)
        removed = m.uninstall(client, a.key)
        _out(args, {"key": a.key, "removed": removed}, f"removed {a.name}: {', '.join(removed)}")
    return 0


def cmd_pref(m: Manager, args) -> int:
    client = m.client(args.client)
    a = _find_addon(m, client, args.addon)
    values = {
        "pin": {"pinned": True}, "unpin": {"pinned": False},
        "ignore": {"ignored": True}, "unignore": {"ignored": False},
    }.get(args.cmd) or {"channel": args.channel}
    m.set_pref(client, a.key, **values)
    _out(args, {"key": a.key, **values}, f"{a.name}: " + ", ".join(f"{k}={v}" for k, v in values.items()))
    return 0


def cmd_backup(m: Manager, args) -> int:
    client = m.client(args.client)
    if args.action == "create":
        b = m.backup(client)
        _out(args, b.to_dict() if b else None, f"backed up to {b.path}" if b else "no WTF folder to back up")
    elif args.action == "list":
        bs = m.backups(client)
        rows = [[b.id, time.strftime("%Y-%m-%d %H:%M", time.localtime(b.created)), b.reason, f"{b.size / 1e6:.1f} MB"] for b in bs]
        _out(args, [b.to_dict() for b in bs], _table(rows, ["ID", "CREATED", "REASON", "SIZE"]) if rows else "no backups")
    else:
        if not args.id:
            raise ManagerError("backup restore needs a backup id (see `omaforge backup list`)")
        safety = m.restore(client, args.id)
        _out(args, {"restored": args.id, "safety": safety.to_dict() if safety else None},
             f"restored {args.id}" + (f"; previous WTF saved as {safety.id}" if safety else ""))
    return 0


def cmd_export(m: Manager, args) -> int:
    client = m.client(args.client)
    data = m.export(client)
    text = json.dumps(data, indent=2) + "\n"
    if args.file and args.file != "-":
        Path(args.file).write_text(text)
        print(f"exported {len(data['addons'])} addons to {args.file}"
              + (f" ({len(data['unknown'])} unknown addons listed but not re-installable)" if data["unknown"] else ""))
    else:
        sys.stdout.write(text)
    return 0


def cmd_import(m: Manager, args) -> int:
    client = m.client(args.client)
    data = json.loads(sys.stdin.read() if args.file == "-" else Path(args.file).read_text())
    progress = None if args.json else (lambda e: print(f"installing {e.get('name', e['id'])}", flush=True))
    results = m.import_list(client, data, progress)
    lines = [f"{'ok      ' if r.ok else 'failed  '}{r.name}: {r.new or r.skipped or r.error}" for r in results]
    _out(args, [r.to_dict() for r in results], "\n".join(lines) or "nothing to import")
    return 0 if all(r.ok for r in results) else 1


def cmd_roots(m: Manager, args) -> int:
    if args.action == "add":
        root = m.roots_add(args.path)
        print(f"added {root}")
    elif args.action == "remove":
        m.roots_remove(args.path)
        print(f"removed {args.path}")
    roots = sorted({str(c.root) for c in m.clients(refresh=True)})
    _out(args, {"roots": roots, "manual": m.cfg["roots"]["paths"]},
         "\n".join(roots) if args.action == "list" else "")
    return 0


def cmd_providers(m: Manager, args) -> int:
    rows = [[p.name, p.label, "yes" if p.available else "no",
             p.unavailable_reason or ("built-in key" if p.config.get("builtin") else "")] for p in m.providers.values()]
    _out(args, [{"name": r[0], "available": r[2] == "yes", "reason": r[3]} for r in rows],
         _table(rows, ["NAME", "PROVIDER", "AVAILABLE", "NOTE"]))
    return 0


def cmd_setup(m, args) -> int:
    from omaforge import integration

    home = Path.home()
    try:
        if args.remove:
            menu = integration.remove_menu(home)
            bind = integration.remove_binding(home)
            print("removed omaforge from the Omarchy menu" if menu else "no menu entry to remove")
            print("removed the omaforge keybinding" if bind else "no keybinding to remove")
            return 0
        path = integration.install_menu(home)
        print(f"added \"WoW Addons\" to the Omarchy menu ({path})")
        if args.keybind:
            path = integration.install_binding(home, args.keybind)
            print(f"bound {integration.normalize_keys(args.keybind)} to omaforge ({path})")
    except integration.SetupError as e:
        print(f"omaforge: {e}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="omaforge", description="World of Warcraft addon manager for Omarchy. "
                                "Run without arguments to open the app.")
    p.add_argument("--version", action="version", version=f"omaforge {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--client", help="client key, folder (retail, classic_beta) or game (forever)")
    common.add_argument("--json", action="store_true", help="machine-readable output")
    common.add_argument("--offline", action="store_true", help="use cached provider data only")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("clients", parents=[common], help="list detected WoW clients").set_defaults(fn=cmd_clients)
    s = sub.add_parser("list", parents=[common], help="list installed addons")
    s.add_argument("--check", action="store_true", help="also check for updates")
    s.set_defaults(fn=cmd_list)
    s = sub.add_parser("check", parents=[common], help="check for updates")
    s.set_defaults(fn=cmd_list, check=True)
    s = sub.add_parser("update", parents=[common], help="update addons")
    s.add_argument("addons", nargs="*", help="addons to update (key, folder or name)")
    s.add_argument("--all", action="store_true", help="update everything not pinned or ignored")
    s.add_argument("--no-backup", action="store_true", help="skip the WTF backup before a bulk update")
    s.add_argument("--notify", action="store_true", help="send a desktop notification with the result")
    s.set_defaults(fn=cmd_update)
    s = sub.add_parser("search", parents=[common], help="search enabled providers")
    s.add_argument("query", nargs="+")
    s.add_argument("-p", "--provider", action="append", help="limit to a provider (repeatable)")
    s.add_argument("-n", "--limit", type=int, default=25)
    s.set_defaults(fn=cmd_search)
    s = sub.add_parser("install", parents=[common], help="install addons (provider:id)")
    s.add_argument("addons", nargs="+")
    s.add_argument("--channel", choices=CHANNELS)
    s.add_argument("--force", action="store_true", help="take over folders owned by another addon")
    s.set_defaults(fn=cmd_install)
    s = sub.add_parser("uninstall", parents=[common], help="remove addons and all their folders")
    s.add_argument("addons", nargs="+")
    s.set_defaults(fn=cmd_uninstall)
    for name, desc in (("pin", "keep an addon at its version"), ("unpin", "allow updates again"),
                       ("ignore", "hide an addon from update checks"), ("unignore", "check it again")):
        s = sub.add_parser(name, parents=[common], help=desc)
        s.add_argument("addon")
        s.set_defaults(fn=cmd_pref)
    s = sub.add_parser("channel", parents=[common], help="set an addon's release channel")
    s.add_argument("addon")
    s.add_argument("channel", choices=CHANNELS)
    s.set_defaults(fn=cmd_pref)
    s = sub.add_parser("backup", parents=[common], help="back up or restore the WTF folder")
    s.add_argument("action", nargs="?", choices=("create", "list", "restore"), default="create")
    s.add_argument("id", nargs="?")
    s.set_defaults(fn=cmd_backup)
    s = sub.add_parser("export", parents=[common], help="export the addon list as JSON")
    s.add_argument("file", nargs="?", default="-")
    s.set_defaults(fn=cmd_export)
    s = sub.add_parser("import", parents=[common], help="install addons from an exported list")
    s.add_argument("file")
    s.set_defaults(fn=cmd_import)
    s = sub.add_parser("roots", parents=[common], help="list, add or remove install roots")
    s.add_argument("action", nargs="?", choices=("list", "add", "remove"), default="list")
    s.add_argument("path", nargs="?")
    s.set_defaults(fn=cmd_roots)
    sub.add_parser("providers", parents=[common], help="show provider status").set_defaults(fn=cmd_providers)
    s = sub.add_parser("setup", help="integrate with Omarchy (menu entry, optional keybinding)")
    s.add_argument("target", choices=("omarchy",))
    s.add_argument("--keybind", metavar="KEYS", help="also bind a key, e.g. 'SUPER + SHIFT + Z'")
    s.add_argument("--remove", action="store_true", help="undo the integration")
    s.set_defaults(fn=cmd_setup, json=False, offline=False, client=None)
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "roots" and args.action in ("add", "remove") and not args.path:
        print("roots add/remove needs a path", file=sys.stderr)
        return 2
    if args.cmd == "setup":
        return cmd_setup(None, args)
    try:
        m = Manager()
        if args.offline:
            m.http.offline = True
        return args.fn(m, args)
    except (ManagerError, ProviderError, HttpError, InstallError, BackupError) as e:
        print(f"omaforge: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
