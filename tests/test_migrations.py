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


def test_users_migration_contains_required_auth_schema() -> None:
    migration = PROJECT_ROOT / "migrations/0002_create_users_and_link_history.sql"

    sql = migration.read_text(encoding="utf-8").lower()

    assert "create table if not exists users" in sql
    assert "id bigserial primary key" in sql
    assert "email varchar(255) not null" in sql
    assert "hashed_password text not null" in sql
    assert "is_active boolean not null default true" in sql
    assert "is_admin boolean not null default false" in sql
    assert "created_at timestamptz not null default now()" in sql
    assert "on users (lower(email))" in sql
    assert "add column if not exists user_id bigint" in sql
    assert "foreign key (user_id)" in sql
    assert "references users (id)" in sql


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
