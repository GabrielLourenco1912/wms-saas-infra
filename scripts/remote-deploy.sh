#!/usr/bin/env bash
# Runs on the Ubuntu host. Configuration is read by Compose, never source/eval.
set +x
set -Eeuo pipefail
umask 077

release_dir=${1:?Informe o diretório da release}
project=${2:?Informe o projeto Compose}
registry_user=${3:?Informe o usuário do GHCR}
wait_timeout=${4:-240}
[[ "$release_dir" == /*/.releases/* && -d "$release_dir" ]] || exit 2
[[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || exit 2
[[ "$registry_user" =~ ^[A-Za-z0-9_-]+(\[bot\])?$ ]] || exit 2
[[ "$wait_timeout" =~ ^[0-9]{2,4}$ ]] && (( 10#$wait_timeout >= 30 && 10#$wait_timeout <= 1800 )) || exit 2
deploy_dir=$(dirname -- "$(dirname -- "$release_dir")")
[[ -f "$release_dir/.env" && -f "$release_dir/compose.deploy.yml" ]] || exit 2
for link in current previous; do
    [[ ! -e "$deploy_dir/$link" || -L "$deploy_dir/$link" ]] || exit 2
done

# Also protects against another workflow/repository deploying to the same path.
exec 9>"$deploy_dir/.deploy.lock"
flock --nonblock 9 || { printf 'Outro deploy está em execução.\n' >&2; exit 75; }
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d "$release_dir/.docker.XXXXXXXX")
next_link="$deploy_dir/.current-$BASHPID"
cleanup() { rm -rf -- "$DOCKER_CONFIG"; rm -f -- "$next_link"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

compose=(docker compose --project-name "$project" --env-file "$release_dir/.env" -f "$release_dir/compose.deploy.yml")
docker info >/dev/null
docker compose version
# Token arrives through SSH stdin; credentials live only until this script exits.
docker login ghcr.io --username "$registry_user" --password-stdin >/dev/null
"${compose[@]}" config --quiet

# Complete every pull and the offline backup preflight before replacing services.
"${compose[@]}" pull backend web mysql-backup
"${compose[@]}" pull --policy missing mysql
"${compose[@]}" run --rm --no-deps -T mysql-backup check
"${compose[@]}" up --detach --no-build --pull never --no-recreate --wait --wait-timeout 180 mysql
# --no-deps keeps the existing database container/configuration intact.
"${compose[@]}" up --detach --no-build --pull never --no-deps --wait --wait-timeout "$wait_timeout" backend web mysql-backup

# Record only successful deployments. No automatic rollback of database migrations.
if [[ -L "$deploy_dir/current" ]]; then
    ln -sfn -- "$(readlink -- "$deploy_dir/current")" "$deploy_dir/previous"
fi
ln -s -- ".releases/${release_dir##*/}" "$next_link"
mv -Tf -- "$next_link" "$deploy_dir/current"
"${compose[@]}" ps
printf 'Deploy concluído: %s\n' "${release_dir##*/}"
