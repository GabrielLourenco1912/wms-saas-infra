#!/usr/bin/env bash
# Runs on Actions; only the Compose manifest, runtime config and deploy script travel.
set +x
set -Eeuo pipefail
umask 077

bundle=${1:?Informe o diretório do pacote}
: "${DEPLOY_HOST:?}" "${DEPLOY_USER:?}" "${DEPLOY_DIR:?}" "${DEPLOY_RELEASE_ID:?}"
: "${DEPLOY_SSH_PRIVATE_KEY:?}" "${DEPLOY_SSH_KNOWN_HOSTS:?}" "${GHCR_TOKEN:?}" "${GHCR_USERNAME:?}"
port=${DEPLOY_PORT:-22}
[[ "$DEPLOY_HOST" =~ ^[A-Za-z0-9.:-]+$ ]] || exit 2
[[ "$DEPLOY_USER" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || exit 2
[[ "$port" =~ ^[0-9]{1,5}$ ]] && (( 10#$port > 0 && 10#$port <= 65535 )) || exit 2
[[ "$DEPLOY_DIR" =~ ^/[A-Za-z0-9_./-]+$ && "$DEPLOY_DIR" != / ]] || exit 2
[[ ! "$DEPLOY_DIR" =~ /\.\.?(/|$) ]] || exit 2
[[ "$DEPLOY_RELEASE_ID" =~ ^[a-zA-Z0-9_-]+$ ]] || exit 2
project=${DEPLOY_PROJECT_NAME:-wms-saas}
wait_timeout=${DEPLOY_WAIT_TIMEOUT:-240}
[[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || exit 2
[[ "$wait_timeout" =~ ^[0-9]{2,4}$ ]] && (( 10#$wait_timeout >= 30 && 10#$wait_timeout <= 1800 )) || exit 2
[[ "$GHCR_USERNAME" =~ ^[A-Za-z0-9_-]+(\[bot\])?$ ]] || exit 2
[[ -f "$bundle/.env" && -f "$bundle/compose.deploy.yml" && -f "$bundle/remote-deploy.sh" ]] || exit 2

ssh_dir=$(mktemp -d)
cleanup() { rm -rf -- "$ssh_dir"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
printf '%s\n' "$DEPLOY_SSH_PRIVATE_KEY" >"$ssh_dir/key"
printf '%s\n' "$DEPLOY_SSH_KNOWN_HOSTS" >"$ssh_dir/known_hosts"
cat >"$ssh_dir/config" <<EOF
Host wms-deploy
    HostName $DEPLOY_HOST
    User $DEPLOY_USER
    Port $port
    IdentityFile $ssh_dir/key
    UserKnownHostsFile $ssh_dir/known_hosts
    StrictHostKeyChecking yes
    IdentitiesOnly yes
    BatchMode yes
    ConnectTimeout 15
    ServerAliveInterval 15
    ServerAliveCountMax 4
EOF
ssh_cmd=(ssh -F "$ssh_dir/config" wms-deploy)
release_dir="${DEPLOY_DIR%/}/.releases/$DEPLOY_RELEASE_ID"
# All remote arguments were restricted above before entering the remote shell.
"${ssh_cmd[@]}" "umask 077; mkdir -p '$DEPLOY_DIR/.releases'; mkdir '$release_dir'"
tar -C "$bundle" -cf - .env compose.deploy.yml remote-deploy.sh |
    "${ssh_cmd[@]}" "tar --no-same-owner -xf - -C '$release_dir'"
printf '%s' "$GHCR_TOKEN" |
    "${ssh_cmd[@]}" "bash '$release_dir/remote-deploy.sh' '$release_dir' '$project' '$GHCR_USERNAME' '$wait_timeout'"
