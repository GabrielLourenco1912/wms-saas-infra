#!/usr/bin/env python3
"""Create disposable credentials without reading the application's .env."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys

import bcrypt

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("renderer", ROOT / "scripts/render-deploy-env.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
destination = Path(sys.argv[1])
destination.mkdir(parents=True, exist_ok=True, mode=0o700)
credentials = {
    "managerEmail": "gestor@homol.wms.local", "operatorEmail": "operador@homol.wms.local",
    "concurrentEmail": "concorrente@homol.wms.local",
    "managerPassword": secrets.token_urlsafe(24), "operatorPassword": secrets.token_urlsafe(24),
    "driverToken": secrets.token_urlsafe(32),
}
runtime = {"DB_PASSWORD": secrets.token_urlsafe(32), "JWT_SECRET": secrets.token_urlsafe(48),
           "HOMOL_MANAGER_PASSWORD_HASH": bcrypt.hashpw(credentials["managerPassword"].encode(), bcrypt.gensalt()).decode(),
           "HOMOL_OPERATOR_PASSWORD_HASH": bcrypt.hashpw(credentials["operatorPassword"].encode(), bcrypt.gensalt()).decode()}
images = {name: "ghcr.io/example/placeholder@sha256:" + "a" * 64 for name in renderer.IMAGE_NAMES}
content = renderer.render({}, runtime, images, "homol")
content += "WMS_TEST_BACKUP_DIR=" + json.dumps(str(destination / "backups")) + "\n"
for name, value in ((".env", content), ("credentials.json", json.dumps(credentials))):
    path = destination / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(value)
print("Credenciais descartáveis geradas; valores omitidos.")
