#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_ID="voice-input-linux"
APP_NAME="Voice Input Linux"
APPSTREAM_ID="io.github.ezhonghu.openshandianshuo.voiceinputlinux"
ARCH="${ARCH:-$(uname -m)}"
VERSION="${VERSION:-$(date +%Y.%m.%d)}"
DIST_DIR="${ROOT}/dist"
BUILD_DIR="${ROOT}/build/appimage"
APPDIR="${BUILD_DIR}/${APP_ID}.AppDir"
CACHE_DIR="${ROOT}/.cache/appimage"
PYTHON_BIN="${PYTHON_BIN:-${ROOT}/.venv/bin/python}"

case "${ARCH}" in
  x86_64|amd64) APPIMAGE_ARCH="x86_64" ;;
  aarch64|arm64) APPIMAGE_ARCH="aarch64" ;;
  *)
    echo "Unsupported ARCH: ${ARCH}" >&2
    exit 2
    ;;
esac

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

echo "Using Python: ${PYTHON_BIN}"
"${PYTHON_BIN}" -m pip install --upgrade pip
"${PYTHON_BIN}" -m pip install -r "${ROOT}/requirements.txt" pyinstaller

rm -rf "${ROOT}/build/pyinstaller" "${DIST_DIR}/${APP_ID}" "${APPDIR}"
mkdir -p "${BUILD_DIR}" "${APPDIR}/usr/opt" "${APPDIR}/usr/share/applications" \
  "${APPDIR}/usr/share/icons/hicolor/scalable/apps" \
  "${APPDIR}/usr/share/metainfo"

"${PYTHON_BIN}" -m PyInstaller \
  --noconfirm \
  --clean \
  --workpath "${ROOT}/build/pyinstaller" \
  --distpath "${DIST_DIR}" \
  "${ROOT}/packaging/pyinstaller/${APP_ID}.spec"

cp -a "${DIST_DIR}/${APP_ID}" "${APPDIR}/usr/opt/${APP_ID}"
install -m 0755 "${ROOT}/packaging/appimage/AppRun" "${APPDIR}/AppRun"

install -m 0755 "${ROOT}/voice_input/resources/${APP_ID}.desktop" \
  "${APPDIR}/${APPSTREAM_ID}.desktop"
install -m 0755 "${ROOT}/voice_input/resources/${APP_ID}.desktop" \
  "${APPDIR}/usr/share/applications/${APPSTREAM_ID}.desktop"
install -m 0644 "${ROOT}/voice_input/resources/${APP_ID}.svg" \
  "${APPDIR}/${APP_ID}.svg"
install -m 0644 "${ROOT}/voice_input/resources/${APP_ID}.svg" \
  "${APPDIR}/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
install -m 0644 "${ROOT}/voice_input/resources/${APP_ID}.appdata.xml" \
  "${APPDIR}/usr/share/metainfo/${APPSTREAM_ID}.appdata.xml"

copy_glibc_lib() {
  local lib_name="$1"
  local dest_name="${2:-${lib_name}}"
  local source=""
  if command -v ldconfig >/dev/null 2>&1; then
    source="$(ldconfig -p 2>/dev/null | awk -v name="${lib_name}" '$1 == name { print $NF; exit }')"
  fi
  if [[ -z "${source}" ]]; then
    for candidate in "/usr/lib/${lib_name}" "/usr/lib64/${lib_name}" "/lib/${lib_name}" "/lib64/${lib_name}"; do
      if [[ -e "${candidate}" ]]; then
        source="${candidate}"
        break
      fi
    done
  fi
  if [[ -z "${source}" ]]; then
    echo "Could not find ${lib_name}" >&2
    return 1
  fi
  if [[ "${lib_name}" == ld-linux-* ]]; then
    install -m 0755 "$(readlink -f "${source}")" "${GLIBC_DIR}/${dest_name}"
  else
    install -m 0644 "$(readlink -f "${source}")" "${GLIBC_DIR}/${dest_name}"
  fi
}

if [[ "${BUNDLE_GLIBC:-0}" == "1" ]]; then
  GLIBC_DIR="${APPDIR}/usr/lib/${APP_ID}/glibc"
  mkdir -p "${GLIBC_DIR}"
  echo "Bundling glibc into AppImage (experimental)"
  case "${APPIMAGE_ARCH}" in
    x86_64)
      copy_glibc_lib "ld-linux-x86-64.so.2"
      ;;
    aarch64)
      copy_glibc_lib "ld-linux-aarch64.so.1"
      ;;
  esac
  for lib in libc.so.6 libpthread.so.0 libdl.so.2 librt.so.1 libm.so.6 libresolv.so.2 libnss_files.so.2 libnss_dns.so.2; do
    copy_glibc_lib "${lib}" || true
  done
  cat >"${GLIBC_DIR}/README.txt" <<EOF
This directory contains an experimental bundled glibc copied from the build host.
It is not the recommended compatibility strategy for AppImage distribution.
Prefer building the AppImage on the oldest Linux distribution you intend to support.
EOF
fi

APPIMAGETOOL="${APPIMAGETOOL:-}"
if [[ -z "${APPIMAGETOOL}" ]]; then
  if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="$(command -v appimagetool)"
  else
    mkdir -p "${CACHE_DIR}"
    APPIMAGETOOL="${CACHE_DIR}/appimagetool-${APPIMAGE_ARCH}.AppImage"
    if [[ ! -x "${APPIMAGETOOL}" ]]; then
      case "${APPIMAGE_ARCH}" in
        x86_64)
          URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
          ;;
        aarch64)
          URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-aarch64.AppImage"
          ;;
      esac
      echo "Downloading appimagetool: ${URL}"
      if command -v curl >/dev/null 2>&1; then
        curl -L "${URL}" -o "${APPIMAGETOOL}"
      else
        wget -O "${APPIMAGETOOL}" "${URL}"
      fi
      chmod +x "${APPIMAGETOOL}"
    fi
  fi
fi

OUT="${DIST_DIR}/VoiceInputLinux-${VERSION}-${APPIMAGE_ARCH}.AppImage"
rm -f "${OUT}"
export ARCH="${APPIMAGE_ARCH}"
export VERSION
export APPIMAGE_EXTRACT_AND_RUN=1
APPIMAGETOOL_ARGS=()
if [[ "${APPSTREAM_CHECK:-0}" != "1" ]]; then
  APPIMAGETOOL_ARGS+=("-n")
fi
"${APPIMAGETOOL}" "${APPIMAGETOOL_ARGS[@]}" "${APPDIR}" "${OUT}"
chmod +x "${OUT}"

echo
echo "Built AppImage:"
echo "  ${OUT}"
echo
echo "Run:"
echo "  ${OUT}"
echo
echo "Install desktop entry and user service:"
echo "  ${OUT} install"
