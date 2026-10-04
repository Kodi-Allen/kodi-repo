#!/usr/bin/env bash
set -euo pipefail

readonly CONFIG_URL='https://privadovpn.com/apps/ovpn_configs.zip'
readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly OUTPUT_DIR="${ROOT_DIR}/config/gluetun/us"
readonly OUTPUT_FILE="${OUTPUT_DIR}/privado-us.ovpn"

profile="${1:-jfk-067.default.ovpn}"
case "${profile}" in
  --list-us)
    mode='list'
    ;;
  */*|*[!A-Za-z0-9._-]*|*.tcp-scramble.ovpn)
    echo 'Invalid profile name. Use a *.default.ovpn basename.' >&2
    exit 2
    ;;
  *.default.ovpn)
    mode='prepare'
    ;;
  *)
    echo 'Invalid profile name. Use a *.default.ovpn basename.' >&2
    exit 2
    ;;
esac

for command in curl unzip getent awk grep; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Missing required command: ${command}" >&2
    exit 1
  fi
done

work_dir="$(mktemp -d)"
trap 'rm -rf "${work_dir}"' EXIT
archive="${work_dir}/ovpn_configs.zip"

curl --fail --location --silent --show-error --retry 2 \
  --output "${archive}" "${CONFIG_URL}"

if [[ "${mode}" == 'list' ]]; then
  unzip -Z1 "${archive}" \
    | awk '/^(atl|dca|den|dfw|dtw|jfk|lax|mia|ord|phx|sea|sjc)-[0-9]+\.default\.ovpn$/'
  exit 0
fi

if ! unzip -Z1 "${archive}" | grep -Fx -- "${profile}" >/dev/null; then
  echo "Profile not found in Privado archive: ${profile}" >&2
  echo 'Run scripts/prepare-privado-us.sh --list-us for current profiles.' >&2
  exit 1
fi

source_file="${work_dir}/${profile}"
unzip -p "${archive}" "${profile}" > "${source_file}"
remote_host="$(awk '$1 == "remote" { print $2; exit }' "${source_file}")"
remote_ip="$(getent ahostsv4 "${remote_host}" | awk 'NR == 1 { print $1 }')"
if [[ -z "${remote_host}" || -z "${remote_ip}" ]]; then
  echo "Could not resolve the VPN endpoint for ${profile}." >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
awk -v host="${remote_host}" -v ip="${remote_ip}" '
  $1 == "remote" && $2 == host { $2 = ip }
  $1 == "route-ipv6" { next }
  $1 == "route" && $2 == "0.0.0.0" { next }
  /^# data-ciphers / { sub(/^# /, "") }
  /^# data-ciphers-fallback / { sub(/^# /, "") }
  { print }
' "${source_file}" > "${OUTPUT_FILE}"
chmod 600 "${OUTPUT_FILE}"

echo "Prepared ${OUTPUT_FILE}"
echo "Profile:  ${profile}"
echo "Endpoint: ${remote_host} -> ${remote_ip}"
