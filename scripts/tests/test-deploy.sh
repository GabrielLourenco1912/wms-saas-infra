#!/usr/bin/env bash
# Test deployment failure boundaries without touching a Docker daemon or SSH host.
set -Eeuo pipefail
test_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
script_dir=$(dirname -- "$test_dir")
test_root=$(mktemp -d)
trap 'rm -rf -- "$test_root"' EXIT
mkdir -p "$test_root/bin" "$test_root/host/.releases/old" "$test_root/host/.releases/new"
export MOCK_LOG="$test_root/docker.log" MOCK_CONFIG="$test_root/docker-config-path"
export MOCK_FAIL=
cat >"$test_root/bin/docker" <<'DOCKER'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' "$*" >> "$MOCK_LOG"
if [[ "$1" == login ]]; then
    token=$(cat)
    [[ "$token" == test-ephemeral-token ]]
    printf '%s' "$DOCKER_CONFIG" > "$MOCK_CONFIG"
    printf '%s' "$token" > "$DOCKER_CONFIG/config.json"
fi
case "$MOCK_FAIL:$*" in
    login:login*|config:*'config --quiet'*|pull:*'pull backend'*|check:*'mysql-backup check'*|health:*'--no-deps --wait'*) exit 1 ;;
esac
DOCKER
chmod +x "$test_root/bin/docker"
export PATH="$test_root/bin:$PATH"
release="$test_root/host/.releases/new"
touch "$release/.env" "$release/compose.deploy.yml"
ln -s .releases/old "$test_root/host/current"

for failure in login config pull check health; do
    export MOCK_FAIL=$failure
    : > "$MOCK_LOG"
    if printf test-ephemeral-token | bash "$script_dir/remote-deploy.sh" "$release" wms-test github-actions >"$test_root/output" 2>&1; then
        printf 'FAIL: %s should fail deployment\n' "$failure" >&2
        exit 1
    fi
    [[ "$(readlink "$test_root/host/current")" == .releases/old ]]
    [[ ! -d "$(cat "$MOCK_CONFIG")" ]]
    if [[ "$failure" != health ]]; then
        if grep -q 'up --detach' "$MOCK_LOG"; then exit 1; fi
    fi
    if grep -q test-ephemeral-token "$test_root/output"; then exit 1; fi
    printf 'PASS: %s failure preserves successful release and removes registry credentials\n' "$failure"
done

export MOCK_FAIL=
: > "$MOCK_LOG"
printf test-ephemeral-token | bash "$script_dir/remote-deploy.sh" "$release" wms-test github-actions >"$test_root/output" 2>&1
[[ "$(readlink "$test_root/host/current")" == .releases/new ]]
[[ "$(readlink "$test_root/host/previous")" == .releases/old ]]
[[ ! -d "$(cat "$MOCK_CONFIG")" ]]
grep -q -- '--no-recreate --wait --wait-timeout 180 mysql' "$MOCK_LOG"
grep -q -- '--no-build --pull never --no-deps --wait --wait-timeout 240 backend web mysql-backup' "$MOCK_LOG"
if grep -Eq '(^| )(build|prune|down)( |$)' "$MOCK_LOG"; then exit 1; fi
if grep -q test-ephemeral-token "$test_root/output"; then exit 1; fi
printf 'PASS: success promotes release, preserves previous and never builds/prunes/stops the stack\n'

exec 8>"$test_root/host/.deploy.lock"
flock --nonblock 8
if printf test-ephemeral-token | bash "$script_dir/remote-deploy.sh" "$release" wms-test github-actions >"$test_root/output" 2>&1; then
    printf 'FAIL: concurrent deployment was accepted\n' >&2
    exit 1
fi
flock --unlock 8
printf 'PASS: concurrent deployments are rejected\n'

# The SSH transport must reject shell metacharacters before contacting a host.
if DEPLOY_HOST='host;exit 0' DEPLOY_USER=ubuntu DEPLOY_DIR=/opt/wms DEPLOY_RELEASE_ID=test \
    DEPLOY_SSH_PRIVATE_KEY=dummy DEPLOY_SSH_KNOWN_HOSTS=dummy GHCR_TOKEN=dummy GHCR_USERNAME=user \
    bash "$script_dir/send-deploy.sh" "$release" >"$test_root/output" 2>&1; then
    printf 'FAIL: unsafe SSH hostname was accepted\n' >&2
    exit 1
fi
printf 'PASS: unsafe SSH input is rejected\n'
