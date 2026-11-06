#!/usr/bin/env python3
"""Render Compose configuration from GitHub vars and explicitly supplied secrets."""

import json
import os
import re
import sys
from pathlib import Path


DEFAULTS = {
    "MYSQL_IMAGE": "mysql:8.0",
    "PUBLISHED_BIND_ADDRESS": "127.0.0.1",
    "BACKEND_PUBLISHED_PORT": "8080", "WEB_PUBLISHED_PORT": "3000",
    "WEB_PORT": "3000", "WEB_HOSTNAME": "0.0.0.0", "NEXT_TELEMETRY_DISABLED": "1",
    "WEB_ORIGIN": "https://wms.lourencogabriel.dev",
    "WMS_API_BASE_URL": "",
    "SPRING_APPLICATION_NAME": "wms-saas", "SPRING_THREADS_VIRTUAL_ENABLED": "true",
    "DB_HOST": "mysql", "DB_PORT": "3306", "DB_NAME": "wms_saas",
    "SPRING_JPA_OPEN_IN_VIEW": "false", "SPRING_JPA_HIBERNATE_DDL_AUTO": "validate",
    "SPRING_JPA_SHOW_SQL": "false", "FLYWAY_BASELINE_ON_MIGRATE": "false",
    "FLYWAY_BASELINE_VERSION": "1",
    "MAIL_HOST": "", "MAIL_PORT": "587", "MAIL_FROM": "no-reply@lourencogabriel.dev",
    "MAIL_SMTP_AUTH": "true", "MAIL_STARTTLS_ENABLED": "true",
    "MAIL_CONNECTION_TIMEOUT": "5000", "MAIL_READ_TIMEOUT": "5000", "MAIL_WRITE_TIMEOUT": "5000",
    "FREEMARKER_TEMPLATE_LOADER_PATH": "classpath:/templates/", "FREEMARKER_SUFFIX": ".ftlh",
    "FREEMARKER_CHARSET": "UTF-8", "FREEMARKER_CHECK_TEMPLATE_LOCATION": "true",
    "SPRING_MVC_PROBLEMDETAILS_ENABLED": "false", "SERVER_PORT": "8080",
    "JWT_ISSUER": "https://wms.lourencogabriel.dev", "CORS_ALLOWED_ORIGINS": "https://wms.lourencogabriel.dev",
    "REFRESH_COOKIE_SECURE": "true",
    "AUTH_CHALLENGE_TTL": "10m", "AUTH_CHALLENGE_MAX_ATTEMPTS": "5",
    "ACCOUNT_LOCK_MAX_FAILED_ATTEMPTS": "5", "ACCOUNT_LOCK_DURATION": "15m",
    "ACCOUNT_LOCK_UNLOCK_INTERVAL": "60000", "ACCOUNT_LOCK_SCHEDULER_ENABLED": "true",
    "WMS_BOOTSTRAP_ENABLED": "true", "WMS_BOOTSTRAP_NAME": "Gabriel Lourenço - adm",
    "MYSQL_BACKUP_HOST_DIR": "/var/backups/wms/mysql", "MYSQL_BACKUP_RETENTION_DAYS": "30",
    "MYSQL_RESTORE_HOST": "", "MYSQL_RESTORE_PORT": "",
}
SECRET_DEFAULTS = {
    "DB_URL": "", "DB_USERNAME": "", "DB_PASSWORD": "", "JWT_SECRET": "",
    "MAIL_USERNAME": "", "MAIL_PASSWORD": "",
    "WMS_BOOTSTRAP_EMAIL": "", "WMS_BOOTSTRAP_PASSWORD": "",
    "MYSQL_BACKUP_USERNAME": "", "MYSQL_BACKUP_PASSWORD": "",
    "MYSQL_RESTORE_USERNAME": "", "MYSQL_RESTORE_PASSWORD": "",
}
IMAGE_NAMES = ("BACKEND_IMAGE", "WEB_IMAGE", "MYSQL_BACKUP_IMAGE")


def render(variables: dict, secrets: dict, images: dict) -> str:
    misplaced = set(variables) & SECRET_DEFAULTS.keys()
    if misplaced:
        raise ValueError("Configure como secrets: " + ", ".join(sorted(misplaced)))
    settings = {name: str(variables.get(name) or default) for name, default in DEFAULTS.items()}
    settings.update({name: secrets.get(name) or default for name, default in SECRET_DEFAULTS.items()})
    for name in ("DB_PASSWORD", "JWT_SECRET", "MAIL_HOST", "MAIL_FROM", "CORS_ALLOWED_ORIGINS"):
        if not settings[name].strip():
            raise ValueError(f"Configuração obrigatória ausente: {name}")
    if len(settings["JWT_SECRET"].encode("utf-8")) < 32:
        raise ValueError("JWT_SECRET precisa ter pelo menos 32 bytes UTF-8")
    if settings["WMS_BOOTSTRAP_ENABLED"].lower() == "true":
        if not all(settings[name] for name in ("WMS_BOOTSTRAP_EMAIL", "WMS_BOOTSTRAP_PASSWORD")):
            raise ValueError("Bootstrap exige WMS_BOOTSTRAP_EMAIL e WMS_BOOTSTRAP_PASSWORD")
    if settings["SPRING_JPA_HIBERNATE_DDL_AUTO"] != "validate":
        raise ValueError("Deploy exige SPRING_JPA_HIBERNATE_DDL_AUTO=validate")
    if settings["FLYWAY_BASELINE_ON_MIGRATE"].lower() != "false":
        raise ValueError("Deploy exige FLYWAY_BASELINE_ON_MIGRATE=false")
    for name in IMAGE_NAMES:
        value = images.get(name, "")
        if not re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}", value):
            raise ValueError(f"Imagem precisa usar um digest GHCR: {name}")
        settings[name] = value
    if any("\0" in value for value in settings.values()):
        raise ValueError("Configuração contém byte NUL")
    # Compose expands $$ to a literal $. JSON quotes preserve quotes, backslashes,
    # Unicode and line breaks without ever executing the value in a shell.
    return "".join(f"{name}={json.dumps(value, ensure_ascii=False).replace('$', '$$')}\n"
                   for name, value in settings.items())


def main() -> None:
    variables = json.loads(os.environ.get("DEPLOY_VARS_JSON", "{}"))
    secrets = {name: os.environ.get(f"WMS_SECRET_{name}", "") for name in SECRET_DEFAULTS}
    images = {name: os.environ.get(name, "") for name in IMAGE_NAMES}
    content = render(variables, secrets, images)
    destination = Path(sys.argv[1])
    # Create a private, new file; refuse to follow an existing symlink.
    with open(destination, "x", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        stream.write(content)
    print("Configuração de deploy gerada (valores omitidos).")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(str(error))
