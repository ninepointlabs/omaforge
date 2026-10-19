#!/usr/bin/env bash
# Build the AppImage into dist/ in an Ubuntu 22.04 container, the same way CI does.
#
#   scripts/build-appimage.sh [--test]
#
# --test   then run packaging/appimage/smoke.sh on it, in the same container.
#
# Needs Docker. Nothing is installed on this computer. Builds the working tree,
# without a CurseForge key unless $OMAFORGE_CURSEFORGE_BUILD_KEY is set.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
run_tests=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --test) run_tests=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

docker run --rm -v "$here:/src" -w /src -e OWNER="$(id -u):$(id -g)" -e TEST="$run_tests" -e OMAFORGE_CURSEFORGE_BUILD_KEY ubuntu:22.04 bash -euc '
  trap "chown -R \"\$OWNER\" dist build 2>/dev/null || true" EXIT
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >/dev/null
  apt-get install -y -qq --no-install-recommends $(cat packaging/appimage/apt-packages.txt | sed "s/#.*//") >/dev/null
  packaging/appimage/build.sh
  if [[ "$TEST" == 1 ]]; then
    packaging/appimage/smoke.sh dist/omaforge-*-x86_64.AppImage
  fi
'
