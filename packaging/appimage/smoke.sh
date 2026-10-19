#!/usr/bin/env bash
# Check a built AppImage the way someone on another distro would meet it.
#
#   packaging/appimage/smoke.sh dist/omaforge-<version>-x86_64.AppImage
#
# Runs without FUSE (APPIMAGE_EXTRACT_AND_RUN), so it works in containers and CI.
# Needs what packaging/appimage/apt-packages.txt lists (Xvfb, xdotool, xprop...).
# SMOKE_OFFLINE=1 skips the two checks that reach the internet.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
image="$(readlink -f "${1:?usage: smoke.sh <AppImage>}")"
export APPIMAGE_EXTRACT_AND_RUN=1
work="$(mktemp -d)"
trap 'kill "${xvfb_pid:-}" 2>/dev/null || true; rm -rf "$work"' EXIT
cd "$work"
failures=0
ok() { echo "ok: $*"; }
fail() { echo "FAIL: $*" >&2; failures=$((failures + 1)); }
# Words that mean something went wrong at start-up (missing plugin, QML module, import...).
problems='error|not installed|cannot|failed|traceback|could not'
# Keep the app's own files (config, cache, state) inside the scratch folder.
export HOME="$work/home" XDG_CONFIG_HOME="$work/home/.config" XDG_CACHE_HOME="$work/home/.cache" \
  XDG_DATA_HOME="$work/home/.local/share" XDG_STATE_HOME="$work/home/.local/state"
mkdir -p "$HOME"

"$image" --appimage-extract >/dev/null
appdir="$work/squashfs-root"
python="$appdir/opt/python3.12/bin/python3.12"

echo "== Desktop entry, metainfo and icons inside"
desktop-file-validate "$appdir/omaforge.desktop" && desktop-file-validate "$appdir/usr/share/applications/omaforge.desktop" \
  && ok "desktop files validate" || fail "desktop-file-validate"
grep -q '^X-AppImage-Version=' "$appdir/omaforge.desktop" && ok "X-AppImage-Version set" || fail "no X-AppImage-Version"
if appstreamcli validate --no-net "$appdir/usr/share/metainfo/omaforge.appdata.xml"; then
  ok "metainfo validates"
else
  fail "appstreamcli validate"
fi
for size in 16 24 32 48 64 128 256 512; do
  png="$appdir/usr/share/icons/hicolor/${size}x${size}/apps/omaforge.png"
  file "$png" | grep -q "PNG image data, $size x $size" || fail "icon $size: $(file -b "$png" 2>&1)"
done
[[ -f "$appdir/usr/share/icons/hicolor/scalable/apps/omaforge.svg" && -f "$appdir/omaforge.svg" ]] || fail "SVG icon missing"
file -L "$appdir/.DirIcon" | grep -q "PNG image data, 256 x 256" || fail ".DirIcon is not the 256px PNG"
ok "icons: 16-512 PNGs, scalable SVG, root icon, .DirIcon"

echo "== Every QML file compiles against the bundled Qt"
"$python" -I "$here/packaging/appimage/check_qml.py" && ok "QML" || fail "QML imports missing from the bundle"

echo "== Command line"
"$image" --version >version.txt 2>&1 && grep -q . version.txt && ok "--version: $(cat version.txt)" || fail "--version: $(cat version.txt)"
"$image" --help >/dev/null && ok "--help" || fail "--help"
"$image" clients >clients.txt 2>&1 && ok "clients (none found, as expected)" || fail "clients: $(cat clients.txt)"
"$image" providers >providers.txt 2>&1 && grep -qi wowinterface providers.txt && ok "providers" || fail "providers: $(cat providers.txt)"
if "$image" setup omarchy >setup.txt 2>&1; then
  fail "setup omarchy should refuse without Omarchy"
else
  grep -q "only applies to Omarchy" setup.txt && ! grep -qi traceback setup.txt \
    && ok "setup omarchy refuses kindly off Omarchy" || fail "setup omarchy: $(cat setup.txt)"
fi
[[ ! -e "$HOME/.config/omarchy" && ! -e "$HOME/.config/hypr" ]] && ok "wrote no Omarchy or Hyprland config" \
  || fail "touched Omarchy/Hyprland config"

echo "== HTTPS from Python and from Qt"
if [[ "${SMOKE_OFFLINE:-0}" == 1 ]]; then
  echo "skipped (SMOKE_OFFLINE=1)"
else
  # Without SSL_CERT_FILE, the way the app runs: omaforge must find the system's CA bundle itself.
  env -u SSL_CERT_FILE -u SSL_CERT_DIR "$python" -I -c '
from omaforge.core.http import Http
r = Http(offline=False).get("https://api.github.com/zen", cache=False)
assert r.status == 200 and r.body, r
' && ok "Python HTTPS with the system CA certificates" || fail "Python HTTPS"
  QT_QPA_PLATFORM=offscreen "$python" -I -c '
import sys
from PySide6.QtCore import QCoreApplication, QUrl, QTimer
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QSslSocket
app = QCoreApplication(["omaforge"])
assert QSslSocket.supportsSsl(), "no TLS backend"
manager = QNetworkAccessManager()  # keep a reference: the reply dies with it
reply = manager.get(QNetworkRequest(QUrl("https://api.github.com/zen")))
reply.finished.connect(app.quit)
QTimer.singleShot(20000, app.quit)
app.exec()
sys.exit(0 if reply.error().name == "NoError" else f"Qt HTTPS: {reply.errorString()}")
' && ok "Qt HTTPS (addon images): TLS backend loads, certificate accepted" || fail "Qt HTTPS"
fi

echo "== The window, offscreen (the release workflow's self-test)"
set +e
QT_QPA_PLATFORM=offscreen OMAFORGE_SELFTEST=1 timeout 30 "$image" >selftest.log 2>&1
rc=$?
set -e
if [[ $rc == 0 ]] && grep -q "interface loaded" selftest.log && ! grep -Eiq "$problems" selftest.log; then
  ok "interface loads offscreen"
else
  fail "self-test (exit $rc): $(cat selftest.log)"
fi

echo "== The window on X11 (Xvfb), with no Omarchy, no Hyprland and an empty home"
Xvfb :77 -screen 0 1280x800x24 -nolisten tcp >/dev/null 2>&1 &
xvfb_pid=$!
sleep 1
fresh_home="$(mktemp -d)"
env -i DISPLAY=:77 HOME="$fresh_home" PATH=/usr/bin:/bin APPIMAGE_EXTRACT_AND_RUN=1 LANG=C.UTF-8 \
  "$image" >x11.log 2>&1 &
app_pid=$!
wid="$(DISPLAY=:77 timeout 30 xdotool search --sync --onlyvisible --classname '^omaforge$' 2>/dev/null | head -1 || true)"
if [[ -n "$wid" ]]; then
  wm_class="$(DISPLAY=:77 xprop -id "$wid" WM_CLASS)"
  wanted="$(sed -n 's/^StartupWMClass=//p' "$appdir/omaforge.desktop")"
  if grep -q "\"$wanted\"" <<<"$wm_class"; then
    ok "WM_CLASS ($wm_class) has StartupWMClass=$wanted"
  elif [[ "${SMOKE_WM_CLASS_WARN_ONLY:-0}" == 1 ]]; then
    echo "warning: WM_CLASS $wm_class does not match StartupWMClass=$wanted (this version predates the fix)"
  else
    fail "WM_CLASS $wm_class does not match StartupWMClass=$wanted"
  fi
  win_pid="$(DISPLAY=:77 xdotool getwindowpid "$wid")"
  leaked="$(tr '\0' '\n' <"/proc/$win_pid/environ" | grep -E '^(LD_LIBRARY_PATH|LD_PRELOAD|PYTHONHOME|PYTHONPATH|QT_PLUGIN_PATH|QML2_IMPORT_PATH|QML_IMPORT_PATH|XDG_DATA_DIRS|SSL_CERT_FILE|TCL_LIBRARY)=' || true)"
  [[ -z "$leaked" ]] && ok "the app's environment (inherited by xdg-open, notify-send...) has nothing from the bundle" \
    || fail "bundle variables leak to child processes: $leaked"
  sleep 2
else
  fail "no window appeared on Xvfb: $(cat x11.log)"
fi
kill "$app_pid" 2>/dev/null || true
pkill -f "$appdir/opt/python3.12" 2>/dev/null || true
pkill -f "appimage_extracted.*/opt/python3.12" 2>/dev/null || true
wait "$app_pid" 2>/dev/null || true
if grep -Eiq "$problems" x11.log; then fail "X11 run printed: $(cat x11.log)"; else ok "X11 run is quiet (theme fell back, no tracebacks)"; fi
[[ ! -e "$fresh_home/.config/omarchy" && ! -e "$fresh_home/.config/hypr" ]] \
  && ok "the window wrote no Omarchy or Hyprland config" || fail "touched Omarchy/Hyprland config in a fresh home"
[[ ! -e "$fresh_home/.config/systemd" ]] && ok "no systemd timer installed" || fail "installed a systemd unit"

echo "== --install-desktop-entry / --remove-desktop-entry"
data="$work/xdg-data"
XDG_DATA_HOME="$data" "$image" --install-desktop-entry
entry="$data/applications/omaforge.desktop"
desktop-file-validate "$entry" && ok "installed entry validates" || fail "installed entry does not validate"
grep -qx "Exec=\"$image\"" "$entry" && grep -qx "TryExec=$image" "$entry" \
  && ok "Exec and TryExec point at the AppImage" || fail "Exec/TryExec: $(grep -E '^(Try)?Exec=' "$entry")"
[[ -f "$data/icons/hicolor/256x256/apps/omaforge.png" && -f "$data/icons/hicolor/scalable/apps/omaforge.svg" ]] \
  && ok "icons installed" || fail "icons missing"
XDG_DATA_HOME="$data" "$image" --install-desktop-entry >/dev/null && ok "install is idempotent" || fail "second install"
XDG_DATA_HOME="$data" "$image" --remove-desktop-entry
left="$(find "$data" -type f -name 'omaforge*' 2>/dev/null)"
[[ -z "$left" ]] && ok "remove takes every file away" || fail "left behind: $left"
"$appdir/AppRun" --install-desktop-entry >/dev/null 2>&1 && fail "install from an extracted AppDir should refuse" \
  || ok "install from an extracted AppDir refuses kindly"

echo
if [[ $failures -gt 0 ]]; then
  echo "$failures check(s) failed." >&2
  exit 1
fi
echo "All AppImage checks passed. Size: $(du -h "$image" | cut -f1)"
