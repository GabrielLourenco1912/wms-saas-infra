#!/usr/bin/env python3
"""Run the Android driver without placing credentials in published artifacts."""
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
credential_file = Path(os.environ["HOMOL_CREDENTIALS_FILE"])
credentials = json.loads(credential_file.read_text())
arguments = ["flutter", "drive", "--no-pub", "-d", os.environ.get("HOMOL_ANDROID_DEVICE", "emulator-5580"),
             "--driver=test_driver/homol_driver.dart", "--target=integration_test/homol_cycle_test.dart",
             "--dart-define=API_BASE_URL=" + os.environ.get("HOMOL_MOBILE_API_URL", "http://10.0.2.2:8888"),
             "--dart-define=CAPTURE_FEEDBACK_METRICS=true",
             "--dart-define=HOMOL_DRIVER_URL=" + os.environ.get("HOMOL_DRIVER_URL", "http://10.0.2.2:8777"),
             "--dart-define=HOMOL_DRIVER_TOKEN=" + credentials["driverToken"]]
subprocess.run(["flutter", "pub", "get", "--enforce-lockfile"], cwd=root / "wms_saas_mobile", check=True,
               stdout=subprocess.DEVNULL)
log_path = credential_file.parent / "mobile-drive.log"
with log_path.open("w") as log:
    result = subprocess.run(arguments, cwd=root / "wms_saas_mobile", stdout=log, stderr=subprocess.STDOUT)
if result.returncode:
    text = "\n".join(log_path.read_text().splitlines()[-60:])
    for name in ("driverToken", "managerPassword", "operatorPassword"):
        text = text.replace(credentials[name], "<redacted>")
    print(text)
raise SystemExit(result.returncode)
