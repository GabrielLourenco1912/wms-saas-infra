#!/usr/bin/env bash
# Self-contained acceptance against disposable real services. Never reads .env.
set +x
set -Eeuo pipefail
umask 077
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
mkdir -p .homol-private
private_dir=$(mktemp -d "$root/.homol-private/acceptance.XXXXXXXX")
run_id=$(date -u +%Y%m%dT%H%M%S)-$RANDOM
project="wms-acceptance-${run_id,,}"
export HOMOL_RUN_ID=$run_id
export HOMOL_ARTIFACT_DIR=${HOMOL_ARTIFACT_DIR:-"$root/artifacts/homol/$run_id"}
export HOMOL_CREDENTIALS_FILE="$private_dir/credentials.json"
export HOMOL_BENCHMARK_PLAN="$private_dir/benchmark-plan.json"
mkdir -p "$HOMOL_ARTIFACT_DIR"
python=${PYTHON:-python3}
# Fail before creating services if a previous test driver still owns the port.
node -e 'const server = require("node:net").createServer(); server.once("error", () => { console.error("A porta 8777 do driver de teste precisa estar livre."); process.exit(1); }); server.listen(8777, "127.0.0.1", () => server.close());'
"$python" tests/homol/prepare-local.py "$private_dir"
compose=(docker compose --project-name "$project" --env-file "$private_dir/.env" -f compose.homol.yml -f tests/homol/compose.local.yml)
driver_pid=
cleanup() {
    result=$?
    trap - EXIT
    if [[ -n "$driver_pid" ]]; then kill "$driver_pid" 2>/dev/null || true; wait "$driver_pid" 2>/dev/null || true; fi
    "$python" tests/homol/write-manifest.py || true
    if [[ "${HOMOL_KEEP_ENVIRONMENT:-0}" != 1 ]]; then
        "${compose[@]}" down --volumes >"$private_dir/cleanup.log" 2>&1 || true
    fi
    printf 'Aceitação terminou com código %s. Evidências: %s\n' "$result" "$HOMOL_ARTIFACT_DIR"
    exit "$result"
}
trap cleanup EXIT
"${compose[@]}" config --quiet
"${compose[@]}" build >"$private_dir/build.log" 2>&1
"${compose[@]}" up -d --no-build --wait --wait-timeout 240 >"$private_dir/up.log" 2>&1
node tests/homol/acceptance.mjs >"$private_dir/driver.log" 2>&1 &
driver_pid=$!
for _attempt in {1..120}; do
    if ! kill -0 "$driver_pid" 2>/dev/null; then cat "$private_dir/driver.log"; exit 1; fi
    if grep -q 'Driver de aceitação pronto' "$private_dir/driver.log"; then break; fi
    sleep 1
done
grep -q 'Driver de aceitação pronto' "$private_dir/driver.log"
"$python" tests/homol/run-mobile.py
node tests/homol/prepare-benchmark.mjs
benchmark_result=0
for phase in baseline concurrent; do
    if docker run --rm --network host --user "$(id -u):$(id -g)" \
        -e MODE="$phase" \
        -v "$private_dir/benchmark-plan.json:/private/benchmark-plan.json:ro" \
        -v "$root/tests/homol:/scripts:ro" \
        -v "$HOMOL_ARTIFACT_DIR:/artifacts" \
        "${K6_IMAGE:-grafana/k6:1.3.0}" run --quiet \
        --out "json=/artifacts/benchmark-$phase-samples.json" /scripts/waves.k6.js; then
        :
    else
        benchmark_result=$?
    fi
done
node tests/homol/analyze-benchmark.mjs
"$python" tests/homol/write-manifest.py
"$python" tests/homol/report.py "$HOMOL_ARTIFACT_DIR"
if [[ "$benchmark_result" != 0 ]]; then exit "$benchmark_result"; fi
printf 'Ciclo web/Android, cenários de API e benchmark aprovados.\n'
