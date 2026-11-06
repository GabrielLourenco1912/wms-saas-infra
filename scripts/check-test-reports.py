#!/usr/bin/env python3
"""Fail CI when Maven succeeds by silently skipping Docker-dependent tests."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def check(directory: Path) -> None:
    reports = list(directory.glob("TEST-*.xml"))
    if not reports:
        raise ValueError("Nenhum relatório Surefire encontrado")
    suites = [ET.parse(report).getroot() for report in reports]
    required = {"OutboundMySqlIntegrationTest", "TokenServiceConcurrencyIntegrationTest"}
    if (directory.parent.parent / "src/test/java/dev/lourencogabriel/wmssaas/homol/HomologationMigrationIntegrationTest.java").exists():
        required.add("HomologationMigrationIntegrationTest")
    executed = set()
    total = 0
    for suite in suites:
        name = suite.attrib["name"].rsplit(".", 1)[-1]
        tests = int(suite.get("tests", "0"))
        if any(int(suite.get(field, "0")) for field in ("failures", "errors", "skipped")):
            raise ValueError(f"Há falhas, erros ou testes ignorados em {name}")
        if tests:
            executed.add(name)
            total += tests
    if required - executed:
        raise ValueError("As suítes MySQL precisam executar com Docker: " + ", ".join(sorted(required - executed)))
    print(f"{total} testes aprovados, incluindo MySQL, sem testes ignorados.")


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1] if len(sys.argv) > 1 else "wms-saas-backend/target/surefire-reports"))
    except (ValueError, ET.ParseError) as error:
        sys.exit(str(error))
