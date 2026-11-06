import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


renderer = load_script("render-deploy-env")
reports = load_script("check-test-reports")


class DeployConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.variables = {
            "MAIL_HOST": "smtp.example.test", "MAIL_FROM": "wms@example.test",
            "CORS_ALLOWED_ORIGINS": "https://wms.example.test",
            # General configuration tests do not provision an initial account.
            "WMS_BOOTSTRAP_ENABLED": "false",
        }
        self.secrets = {"DB_PASSWORD": "test-password", "JWT_SECRET": "x" * 32}
        self.images = {name: f"ghcr.io/example/{name.lower()}@sha256:{'a' * 64}"
                       for name in renderer.IMAGE_NAMES}

    def run_renderer(self, destination):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "render-deploy-env.py"), str(destination)],
            env={"DEPLOY_VARS_JSON": json.dumps(self.variables), **self.images,
                 **{f"WMS_SECRET_{name}": value for name, value in self.secrets.items()}},
            umask=0, text=True, capture_output=True,
        )

    def test_cli_creates_private_configuration_without_logging_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / ".env"
            result = self.run_renderer(destination)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(renderer.render(self.variables, self.secrets, self.images),
                             destination.read_text(encoding="utf-8"))
            self.assertEqual(0o600, stat.S_IMODE(destination.stat().st_mode))
            for value in self.secrets.values():
                self.assertNotIn(value, result.stdout + result.stderr)

    def test_cli_refuses_to_overwrite_existing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / ".env"
            destination.write_text("existing configuration", encoding="utf-8")
            result = self.run_renderer(destination)
            self.assertNotEqual(0, result.returncode)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual("existing configuration", destination.read_text(encoding="utf-8"))

    def test_cli_refuses_existing_and_dangling_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            for exists in (True, False):
                with self.subTest(target_exists=exists):
                    target = Path(directory) / f"target-{exists}"
                    if exists:
                        target.write_text("existing configuration", encoding="utf-8")
                    destination = Path(directory) / f"config-{exists}"
                    destination.symlink_to(target)
                    result = self.run_renderer(destination)
                    self.assertNotEqual(0, result.returncode)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertTrue(destination.is_symlink())
                    if exists:
                        self.assertEqual("existing configuration", target.read_text(encoding="utf-8"))
                    else:
                        self.assertFalse(target.exists())

    def compose_config(self, content, manifest="compose.deploy.yml"):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(content)
            # Keep the developer's environment and real .env out of this check.
            result = subprocess.run(
                ["docker", "compose", "--env-file", str(env_file), "--project-name", "wms-ci-test",
                 "-f", str(ROOT / manifest), "config", "--format", "json"],
                env={name: os.environ[name] for name in ("PATH", "HOME") if name in os.environ},
                text=True, capture_output=True,
            )
            if result.returncode:
                self.fail(f"docker compose config falhou:\n{result.stderr.strip()}")
        return json.loads(result.stdout)

    def test_passwords_survive_compose_without_interpolation_or_execution(self):
        values = [
            'áé # $HOME ${DB_NAME} $$ \' " `tick` $(exit 7) \\path',
            "quote\\'end", 'double\\"end', "line1\nline2\tend", "backslash\\",
        ]
        for value in values:
            with self.subTest(value=value):
                self.secrets["DB_PASSWORD"] = value
                config = self.compose_config(renderer.render(self.variables, self.secrets, self.images))
                # `compose config` escapes literal dollars for its reusable output.
                self.assertEqual(value, config["services"]["backend"]["environment"]["DB_PASSWORD"].replace("$$", "$"))
                self.assertEqual(value, config["services"]["mysql"]["environment"]["MYSQL_ROOT_PASSWORD"].replace("$$", "$"))
                self.assertEqual(value, config["services"]["mysql-backup"]["environment"]["MYSQL_BACKUP_PASSWORD"].replace("$$", "$"))

    def test_runtime_manifest_is_isolated_and_uses_pinned_images(self):
        config = self.compose_config(renderer.render(self.variables, self.secrets, self.images))
        for name, service in config["services"].items():
            self.assertNotIn("build", service)
            self.assertNotIn("container_name", service)
            self.assertIn("healthcheck", service)
            if name != "mysql":
                self.assertIn("@sha256:", service["image"])
        for name in ("backend", "web"):
            self.assertEqual("127.0.0.1", config["services"][name]["ports"][0]["host_ip"])
        self.assertNotIn("ports", config["services"]["mysql"])
        self.assertEqual("https://wms.lourencogabriel.dev",
                         config["services"]["web"]["environment"]["WEB_ORIGIN"])

    def test_public_web_origin_and_private_api_share_the_docker_network(self):
        self.variables.update(WEB_ORIGIN="https://wms.example.test:8443", SERVER_PORT="8181",
                              WEB_PORT="3333", WEB_PUBLISHED_PORT="13000")
        content = renderer.render(self.variables, self.secrets, self.images)
        for manifest in ("compose.deploy.yml", "docker-compose.yml"):
            with self.subTest(manifest=manifest):
                config = self.compose_config(content, manifest)
                web = config["services"]["web"]
                backend = config["services"]["backend"]
                self.assertEqual("https://wms.example.test:8443", web["environment"]["WEB_ORIGIN"])
                self.assertEqual("http://backend:8181", web["environment"]["WMS_API_BASE_URL"])
                self.assertIn("default", web["networks"])
                self.assertIn("default", backend["networks"])

    def test_secrets_cannot_be_configured_as_vars(self):
        self.variables["DB_PASSWORD"] = "wrong-place"
        with self.assertRaisesRegex(ValueError, "Configure como secrets: DB_PASSWORD"):
            renderer.render(self.variables, self.secrets, self.images)

    def test_missing_secrets_and_unpinned_images_are_rejected(self):
        for name in ("DB_PASSWORD", "JWT_SECRET"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                renderer.render(self.variables, {**self.secrets, name: ""}, self.images)
        with self.assertRaises(ValueError):
            renderer.render(self.variables, self.secrets, {**self.images, "BACKEND_IMAGE": "ghcr.io/a/b:latest"})

    def test_schema_reset_is_rejected(self):
        for key, value in (("SPRING_JPA_HIBERNATE_DDL_AUTO", "create"),
                           ("FLYWAY_BASELINE_ON_MIGRATE", "true")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                renderer.render({**self.variables, key: value}, self.secrets, self.images)

    def test_enabled_bootstrap_requires_both_credentials(self):
        self.variables["WMS_BOOTSTRAP_ENABLED"] = "true"
        credentials = {"WMS_BOOTSTRAP_EMAIL": "bootstrap@example.test",
                       "WMS_BOOTSTRAP_PASSWORD": "bootstrap-test-password"}
        for missing in (tuple(credentials), ("WMS_BOOTSTRAP_EMAIL",), ("WMS_BOOTSTRAP_PASSWORD",)):
            with self.subTest(missing=missing):
                secrets = {**self.secrets, **credentials, **{name: "" for name in missing}}
                with self.assertRaisesRegex(ValueError, "Bootstrap exige WMS_BOOTSTRAP_EMAIL e WMS_BOOTSTRAP_PASSWORD"):
                    renderer.render(self.variables, secrets, self.images)

    def test_cli_forwards_bootstrap_credentials_without_logging_them(self):
        self.variables["WMS_BOOTSTRAP_ENABLED"] = "true"
        self.secrets.update(WMS_BOOTSTRAP_EMAIL="bootstrap@example.test",
                            WMS_BOOTSTRAP_PASSWORD="bootstrap-test-password")
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / ".env"
            result = self.run_renderer(destination)
            self.assertEqual(0, result.returncode, result.stderr)
            config = self.compose_config(destination.read_text(encoding="utf-8"))
        environment = config["services"]["backend"]["environment"]
        self.assertEqual("true", environment["WMS_BOOTSTRAP_ENABLED"])
        for name in ("WMS_BOOTSTRAP_EMAIL", "WMS_BOOTSTRAP_PASSWORD"):
            self.assertEqual(self.secrets[name], environment[name])
            self.assertNotIn(self.secrets[name], result.stdout + result.stderr)

    def test_custom_ports_and_shared_database_credentials_are_forwarded(self):
        self.variables.update(SERVER_PORT="8181", WEB_PORT="3333", BACKEND_PUBLISHED_PORT="18080",
                              WEB_PUBLISHED_PORT="13000", MAIL_SMTP_AUTH="false")
        self.secrets["DB_USERNAME"] = "application_user"
        config = self.compose_config(renderer.render(self.variables, self.secrets, self.images))
        backend = config["services"]["backend"]
        environment = backend["environment"]
        self.assertEqual(environment["DB_URL"], environment["SPRING_FLYWAY_URL"])
        self.assertEqual(self.secrets["DB_USERNAME"], environment["SPRING_FLYWAY_USER"])
        self.assertEqual(self.secrets["DB_PASSWORD"], environment["SPRING_FLYWAY_PASSWORD"])
        backup = config["services"]["mysql-backup"]["environment"]
        self.assertEqual(self.secrets["DB_USERNAME"], backup["MYSQL_BACKUP_USERNAME"])
        self.assertEqual(self.secrets["DB_PASSWORD"], backup["MYSQL_BACKUP_PASSWORD"])
        self.assertEqual("false", backend["environment"]["MAIL_SMTP_AUTH"])
        self.assertEqual(8181, backend["ports"][0]["target"])
        self.assertEqual("http://backend:8181", config["services"]["web"]["environment"]["WMS_API_BASE_URL"])

    def test_explicit_api_url_is_forwarded(self):
        self.variables.update(SERVER_PORT="8181", WMS_API_BASE_URL="https://api.example.test")
        config = self.compose_config(renderer.render(self.variables, self.secrets, self.images))
        self.assertEqual("https://api.example.test", config["services"]["web"]["environment"]["WMS_API_BASE_URL"])


class HomologationIsolationTest(unittest.TestCase):
    compose_config = DeployConfigurationTest.compose_config
    def setUp(self):
        DeployConfigurationTest.setUp(self)
        self.secrets.update({name: "$2b$12$" + "a" * 53 for name in renderer.HOMOL_SECRET_NAMES})

    def test_homol_ignores_production_ports_origins_database_and_mail_settings(self):
        self.variables.update(WEB_ORIGIN="https://production.invalid", DB_NAME="production",
                              WEB_PUBLISHED_PORT="3000", BACKEND_PUBLISHED_PORT="8080",
                              MAIL_HOST="production.invalid")
        content = renderer.render(self.variables, self.secrets, self.images, "homol")
        config = self.compose_config(content, "compose.homol.yml")
        services = config["services"]
        self.assertEqual(3333, int(services["web"]["ports"][0]["published"]))
        self.assertEqual(8888, int(services["backend"]["ports"][0]["published"]))
        self.assertEqual("127.0.0.1", services["backend"]["ports"][0]["host_ip"])
        self.assertNotIn("ports", services["mysql"])
        self.assertEqual("wms_saas_homol", services["mysql"]["environment"]["MYSQL_DATABASE"])
        self.assertEqual("homol", services["backend"]["environment"]["SPRING_PROFILES_ACTIVE"])
        self.assertEqual("mailpit", services["backend"]["environment"]["MAIL_HOST"])
        self.assertEqual("https://homol.wms.lourencogabriel.dev", services["web"]["environment"]["WEB_ORIGIN"])
        self.assertIn("/var/backups/wms-homol/mysql", content)

    def test_homol_refuses_external_database_and_missing_seed_hashes(self):
        with self.assertRaises(ValueError):
            renderer.render(self.variables, {**self.secrets, "DB_URL": "jdbc:mysql://prod/wms_saas"}, self.images, "homol")
        for name in renderer.HOMOL_SECRET_NAMES:
            with self.subTest(name=name), self.assertRaises(ValueError):
                renderer.render(self.variables, {**self.secrets, name: ""}, self.images, "homol")


class TestReportGateTest(unittest.TestCase):
    def test_empty_or_skipped_mysql_suites_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with self.assertRaises(ValueError):
                reports.check(path)
            (path / "TEST-skipped.xml").write_text(
                '<testsuite name="OutboundMySqlIntegrationTest" tests="1" skipped="1"/>')
            with self.assertRaises(ValueError):
                reports.check(path)
            (path / "TEST-skipped.xml").write_text(
                '<testsuite name="OutboundMySqlIntegrationTest" tests="0"/>')
            with self.assertRaises(ValueError):
                reports.check(path)


if __name__ == "__main__":
    unittest.main()
