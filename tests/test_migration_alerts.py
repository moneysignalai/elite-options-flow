import importlib.util
from pathlib import Path


class StubInspector:
    def has_table(self, name: str, schema=None):
        return name == "alerts"


def test_upgrade_skips_when_alerts_exists(monkeypatch):
    module_path = Path(__file__).parents[1] / "alembic" / "versions" / "0001_create_alerts.py"
    spec = importlib.util.spec_from_file_location("migration_0001", module_path)
    migration = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(migration)  # type: ignore[call-arg]

    inspector = StubInspector()
    monkeypatch.setattr(migration.sa, "inspect", lambda bind: inspector)
    monkeypatch.setattr(migration.op, "get_bind", lambda: object())

    created: list[str] = []
    monkeypatch.setattr(migration.op, "create_table", lambda *args, **kwargs: created.append(args[0]))

    migration.upgrade()

    assert created == []
