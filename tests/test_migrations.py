from pathlib import Path

from scripts.migrate import get_migration_files

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_request_history_migration_contains_required_columns() -> None:
    migration = PROJECT_ROOT / "migrations/0001_create_request_history.sql"

    sql = migration.read_text(encoding="utf-8").lower()

    assert "create table if not exists request_history" in sql
    assert "id bigserial primary key" in sql
    assert "cadastral_number varchar(255) not null" in sql
    assert "latitude double precision not null" in sql
    assert "longitude double precision not null" in sql
    assert "result boolean not null" in sql
    assert "created_at timestamptz not null default now()" in sql


def test_get_migration_files_returns_sql_files_in_order(tmp_path: Path) -> None:
    (tmp_path / "0002_second.sql").write_text("SELECT 2;", encoding="utf-8")
    (tmp_path / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    migration_names = [path.name for path in get_migration_files(tmp_path)]

    assert migration_names == ["0001_first.sql", "0002_second.sql"]


def test_dockerfile_runs_migrations_before_app_start() -> None:
    dockerfile = PROJECT_ROOT / "Dockerfile"

    content = dockerfile.read_text(encoding="utf-8")

    assert "python -m scripts.migrate && uvicorn app.main:app" in content
