#!/usr/bin/env python3
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

root = Path(__file__).resolve().parents[2]
output = Path(os.environ["HOMOL_ARTIFACT_DIR"])
def command(*args):
    return subprocess.check_output(args, cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
revisions = {name: command("git", "-C", str(root / path), "rev-parse", "HEAD")
             for name, path in (("infra", "."), ("backend", "wms-saas-backend"), ("web", "wms-saas-web"), ("mobile", "wms_saas_mobile"))}
working_trees = {name: command("git", "-C", str(root / path), "status", "--porcelain")
                 for name, path in (("infra", "."), ("backend", "wms-saas-backend"), ("web", "wms-saas-web"), ("mobile", "wms_saas_mobile"))}
files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name != "manifest.json"}
data = {"createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "runId": os.environ.get("HOMOL_RUN_ID"),
        "revisions": revisions, "workingTrees": working_trees, "system": platform.platform(), "cpuCount": os.cpu_count(),
        "osRelease": platform.freedesktop_os_release().get("PRETTY_NAME", ""),
        "memoryBytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
        "node": command("node", "--version"), "docker": command("docker", "version", "--format", "{{.Server.Version}}"),
        "androidDevice": os.environ.get("HOMOL_ANDROID_DEVICE", "emulator-5580"),
        "scope": "Synthetic controlled acceptance. Physical camera, gloves, scanner peripherals and production availability are not inferred.",
        "artifactsSha256": files}
(output / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
