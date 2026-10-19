#!/usr/bin/env bash
# Build omaforge's AppImage into dist/: the window and the command line, with
# their own Python 3.12 and Qt, so it runs on any x86_64 Linux with glibc 2.34
# or newer (Ubuntu 22.04, Debian 12, Fedora 39, ...).
#
#   packaging/appimage/build.sh [--out <dir>]
#
# Runs on Ubuntu 22.04: CI's runner, or `scripts/build-appimage.sh` in Docker.
# Needs what packaging/appimage/apt-packages.txt lists: build tools, and the
# X/Wayland libraries Qt links to, so they can be copied in.
#
# With $OMAFORGE_CURSEFORGE_BUILD_KEY set (release builds), the CurseForge key
# is embedded the same way the Arch, .deb and .rpm packages embed it.
#
# Every download is pinned by version and checked against its sha256.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
out="$here/dist"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) out="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

for tool in curl readelf patchelf ldconfig zsyncmake rsvg-convert sha256sum; do
  command -v "$tool" >/dev/null || { echo "build.sh needs $tool" >&2; exit 1; }
done

version="$(sed -n 's/^version = "\(.*\)"/\1/p' "$here/pyproject.toml")"
name="omaforge-$version-x86_64.AppImage"
work="$here/build/appimage"
cache="$work/cache"
appdir="$work/omaforge.AppDir"
mkdir -p "$cache" "$out"

# -- pinned tools -------------------------------------------------------------

python_url=https://github.com/niess/python-appimage/releases/download/python3.12/python3.12.15-cp312-cp312-manylinux_2_28_x86_64.AppImage
python_sha=929ce69b45955bfc74af81fd65a65c3ad240593c99b3574466a94ebf0f987ebf
appimagetool_url=https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage
appimagetool_sha=ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0
runtime_url=https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64
runtime_sha=2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d
# Libraries every desktop already has and that must come from the host (libc, GL drivers...).
excludelist_url=https://raw.githubusercontent.com/AppImageCommunity/pkg2appimage/15a64c20dc23a0154622ba25829364323903b6b5/excludelist
excludelist_sha=50db0f894f34b169c47a5cbc0c17dbab61e9edebca5bc8269a1e6ac1bf4bdad9

fetch() {  # fetch <url> <sha256> <file>
  local file="$cache/$3"
  if [[ ! -f "$file" ]] || ! echo "$2  $file" | sha256sum -c --quiet - 2>/dev/null; then
    curl -fsSL --retry 3 -o "$file.part" "$1"
    echo "$2  $file.part" | sha256sum -c --quiet -
    mv "$file.part" "$file"
  fi
  chmod +x "$file"
}
fetch "$python_url" "$python_sha" python.AppImage
fetch "$appimagetool_url" "$appimagetool_sha" appimagetool.AppImage
fetch "$runtime_url" "$runtime_sha" runtime-x86_64
fetch "$excludelist_url" "$excludelist_sha" excludelist

echo "== Python"
rm -rf "$appdir" "$work/squashfs-root"
(cd "$work" && "$cache/python.AppImage" --appimage-extract >/dev/null)
mv "$work/squashfs-root" "$appdir"
# Keep the interpreter and the libraries it needs; drop python-appimage's own launcher and menu entry.
rm -rf "$appdir"/AppRun "$appdir"/.DirIcon "$appdir"/*.desktop "$appdir"/*.png \
  "${appdir:?}"/usr/bin "$appdir"/usr/share/applications "$appdir"/usr/share/icons "$appdir"/usr/share/metainfo
python="$appdir/opt/python3.12/bin/python3.12"
site="$("$python" -I -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"

echo "== omaforge $version and what it needs"
"$python" -I -m pip install -q --no-warn-script-location --no-compile --no-deps --require-hashes \
  -r "$here/packaging/appimage/requirements.txt"
if [[ -n "${OMAFORGE_CURSEFORGE_BUILD_KEY:-}" ]]; then
  # Written into the tree only for the install below, then removed again.
  "$python" -I "$here/omaforge/buildkey.py" write
  trap 'rm -f "$here/omaforge/_buildkey.py"' EXIT
fi
"$python" -I -m pip install -q --no-warn-script-location --no-compile --no-deps "$here"
rm -f "$here/omaforge/_buildkey.py"
if [[ -f "$site/omaforge/_buildkey.py" ]]; then echo "   CurseForge key embedded"; else echo "   built without a CurseForge key"; fi
"$python" -I -m pip uninstall -q -y pip

echo "== Prune what omaforge does not use"
# The size that matters is Qt. omaforge uses QtCore, QtGui, QtNetwork (QML loads
# addon images over HTTPS), QtSvg, QtQml, QtQuick, QtQuickControls2 and QtQuick.Dialogs.
pyside="$site/PySide6"
qt="$pyside/Qt"
rm -rf "$pyside"/{include,typesystems,glue,scripts,doc,examples,support/generate_pyi.py} \
  "$pyside"/{assistant,designer,linguist,lrelease,lupdate,lconvert,qmlcachegen,qmlformat,qmllint,qmlls,qmlimportscanner,qmltyperegistrar,rcc,uic,balsam,balsamui,svgtoqml,android_deploy,qsb,metaobjectdump.py,project.py} \
  "$qt"/{libexec,translations,metatypes,resources,modules,doc} \
  "$site"/shiboken6_generator
find "$pyside" "$site/shiboken6" -name '*.pyi' -delete
# Python bindings for modules nothing imports, and the Qt libraries only they use.
for module in Qt3D Bluetooth Charts Concurrent DataVisualization DBus Designer Graphs Help HttpServer \
  Location Multimedia Nfc OpenGLWidgets Pdf PdfWidgets Positioning RemoteObjects Scxml Sensors \
  SerialBus SerialPort SpatialAudio Sql StateMachine SvgWidgets Test TextToSpeech UiTools \
  WebChannel WebEngine WebSockets WebView Xml AxContainer Quick3D QuickTest QuickWidgets PrintSupport \
  NetworkAuth; do
  rm -f "$pyside/Qt$module".*.so "$pyside/Qt$module".abi3.so
done
rm -f "$qt"/lib/libQt6{PrintSupport,Designer,DesignerComponents,Help,Pdf,PdfQuick,PdfWidgets,QuickTest,Test,Sql,SvgWidgets,UiTools,ShaderTools,WaylandCompositor,WaylandEglCompositorHwIntegration,QuickParticles,QuickTimeline,QuickTimelineBlendTrees,QmlLS,QmlCompiler,QmlDom,QmlToolingSettings,QmlLint,QmlFormat,LanguageServer,JsonRpc,QuickControlsTestUtils,QuickTestUtils,QmlLocalStorage,QmlXmlListModel,VirtualKeyboard,VirtualKeyboardQml,VirtualKeyboardSettings,Bluetooth,StateMachine,StateMachineQml}.so*
rm -f "$qt"/lib/libQt6{QuickControls2Imagine,QuickControls2ImagineStyleImpl,QuickControls2FluentWinUI3,QuickControls2FluentWinUI3StyleImpl,QuickControls2Material,QuickControls2MaterialStyleImpl,QuickControls2Universal,QuickControls2UniversalStyleImpl,LabsStyleKit,LabsStyleKitImpl,Lottie,LottieVectorImageGenerator,EglFSDeviceIntegration,EglFsKmsSupport,EglFsKmsGbmSupport}.so* \
  "$pyside"/QtLabsStyleKit.abi3.so
# Printing is not used (and CUPS would bring Kerberos and GnuTLS with it); tls/ stays for HTTPS images.
rm -rf "$qt"/plugins/{printsupport,designer,sqldrivers,qmltooling,qmllint,qmlls,egldeviceintegrations,wayland-graphics-integration-server,virtualkeyboard,networkinformation,vectorimageformats,generic,canbus,position,sensors,texttospeech}
# The GTK 3 theme plugin would drag GTK into the bundle; Qt's own GNOME theme and the
# xdg-desktop-portal one (light/dark, file dialogs) cover what omaforge needs from the desktop.
rm -f "$qt"/plugins/platformthemes/libqgtk3.so "$qt"/plugins/imageformats/libqpdf.so \
  "$qt"/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so \
  "$qt"/plugins/platforms/lib{qeglfs,qlinuxfb,qminimalegl,qvnc,qvkkhrdisplay}.so
rm -rf "$qt"/qml/QtQuick/{Particles,Scene2D,Scene3D,VirtualKeyboard,Pdf,Timeline,LocalStorage,tooling} \
  "$qt"/qml/QtQml/{StateMachine,XmlListModel,DesignSupport} "$qt"/qml/QtWayland/Compositor "$qt"/qml/Qt/labs/StyleKit \
  "$qt"/qml/{QtTest,QtCharts,QtGraphs,Qt3D,QtQuick3D,QtMultimedia,QtWebEngine,QtWebView,QtWebSockets,QtWebChannel,QtLocation,QtPositioning,QtSensors,QtTextToSpeech,QtRemoteObjects,QtScxml,QtDataVisualization,Qt5Compat,QtVirtualKeyboard,QtInsight}
# Qt Quick Controls styles other than Basic (which omaforge uses) and Fusion.
for style in "$qt"/qml/QtQuick/Controls/*/; do
  case "$(basename "$style")" in
    Fusion|Basic|impl|designer) ;;
    Imagine|Material|Universal|FluentWinUI3|Windows|macOS|iOS) rm -rf "$style" ;;
  esac
done
rm -rf "$qt"/qml/QtQuick/Controls/designer
# The bundled stdlib's test suite, Tk and the like.
stdlib="$appdir/opt/python3.12/lib/python3.12"
rm -rf "$stdlib"/{test,idlelib,tkinter,turtledemo,ensurepip,lib2to3,pydoc_data} "$stdlib"/lib-dynload/_tkinter*.so \
  "$appdir"/usr/share/tcltk "$appdir"/usr/lib/libtcl* "$appdir"/usr/lib/libtk*
find "$appdir" -name __pycache__ -type d -prune -exec rm -rf {} +

echo "== Bring in the libraries Qt needs that a desktop may not have"
# PySide6's wheels expect xcb-cursor, xkbcommon-x11 and friends from the
# host. Follow each bundled file's NEEDED entries, the way linuxdeploy does:
# a library that is not in the bundle is copied into Qt's lib folder (on every
# Qt library's RUNPATH, and given the same RUNPATH itself), unless the
# excludelist says it must come from the host. Host libraries are not followed,
# so nothing they link to is bundled behind their back.
mapfile -t excluded < <(sed -e 's/#.*//' -e 's/[[:space:]]//g' "$cache/excludelist" | grep .)
declare -A have=()
for lib in "${excluded[@]}"; do have[$lib]=host; done
while IFS= read -r file; do have[$(basename "$file")]=bundled; done \
  < <(find "$appdir" \( -type f -o -type l \) -name '*.so*')
mapfile -t queue < <(find "$appdir" -type f \( -name '*.so' -o -name '*.so.*' -o -path '*/bin/python3.12' \))
missing=()
while [[ ${#queue[@]} -gt 0 ]]; do
  file="${queue[-1]}"; unset 'queue[-1]'
  while IFS= read -r soname; do
    [[ -z "${have[$soname]:-}" ]] || continue
    # awk reads to the end (no early exit), so ldconfig never dies of SIGPIPE under pipefail.
    path="$(ldconfig -p | awk -v s="$soname" '$1 == s && /x86-64/ && !found { print $NF; found = 1 }')"
    if [[ -z "$path" ]]; then
      missing+=("$soname (for ${file#"$appdir"/})"); have[$soname]=missing; continue
    fi
    cp -L "$path" "$qt/lib/$soname"
    patchelf --set-rpath '$ORIGIN' "$qt/lib/$soname"
    have[$soname]=copied
    queue+=("$qt/lib/$soname")
    echo "   + $soname"
  done < <(readelf -d "$file" 2>/dev/null | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p')
done
if [[ ${#missing[@]} -gt 0 ]]; then
  printf '   missing on the build machine: %s\n' "${missing[@]}" >&2
  echo "Install them (packaging/appimage/apt-packages.txt), or prune what needs them, and build again." >&2
  exit 1
fi

echo "== Byte-compile (the AppImage is read-only, so Python cannot cache it later)"
"$python" -I -m compileall -q -j 0 "$appdir/opt/python3.12/lib/python3.12" >/dev/null || true

echo "== Desktop entry, icons, metainfo"
share="$appdir/usr/share"
svg="$here/omaforge/ui/icons/omaforge.svg"
install -Dm644 "$here/packaging/omaforge.desktop" "$share/applications/omaforge.desktop"
echo "X-AppImage-Version=$version" >>"$share/applications/omaforge.desktop"
install -Dm644 "$here/packaging/omaforge.appdata.xml" "$share/metainfo/omaforge.appdata.xml"
install -Dm644 "$svg" "$share/icons/hicolor/scalable/apps/omaforge.svg"
for size in 16 24 32 48 64 128 256 512; do
  mkdir -p "$share/icons/hicolor/${size}x${size}/apps"
  rsvg-convert -w "$size" -h "$size" "$svg" -o "$share/icons/hicolor/${size}x${size}/apps/omaforge.png"
done
install -Dm644 "$here/LICENSE" "$share/licenses/omaforge/LICENSE"
cp "$share/applications/omaforge.desktop" "$appdir/omaforge.desktop"
cp "$svg" "$appdir/omaforge.svg"
ln -sf usr/share/icons/hicolor/256x256/apps/omaforge.png "$appdir/.DirIcon"
install -m755 "$here/packaging/appimage/AppRun" "$appdir/AppRun"
mkdir -p "$appdir/usr/bin"
printf '#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/../../AppRun" "$@"\n' >"$appdir/usr/bin/omaforge"
chmod 755 "$appdir/usr/bin/omaforge"

echo "== AppImage"
rm -f "$out/$name" "$out/$name.zsync" "$out/$name.sha256"
(cd "$out" && ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$cache/appimagetool.AppImage" --no-appstream \
  --runtime-file "$cache/runtime-x86_64" \
  -u "gh-releases-zsync|ninepointlabs|omaforge|latest|omaforge-*x86_64.AppImage.zsync" \
  "$appdir" "$out/$name")
(cd "$out" && sha256sum "$name" >"$name.sha256")
ls -l "$out/$name" "$out/$name.zsync" "$out/$name.sha256"
du -sh "$appdir" | sed 's/^/   unpacked: /'
