import asyncio
from pathlib import Path

import asyncpg

from app.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"

CREATE_SCHEMA_MIGRATIONS_SQL = """
                               CREATE TABLE IF NOT EXISTS schema_migrations
                               (
                                   filename
                                   TEXT
                                   PRIMARY
                                   KEY,
                                   applied_at
                                   TIMESTAMPTZ
                                   NOT
                                   NULL
                                   DEFAULT
                                   NOW
                               (
                               )
                                   ); \
                               """


def get_migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(path for path in migrations_dir.glob("*.sql") if path.is_file())


async def get_applied_migrations(connection: asyncpg.Connection) -> set[str]:
    rows = await connection.fetch("SELECT filename FROM schema_migrations")
    return {row["filename"] for row in rows}


async def apply_migration(
    connection: asyncpg.Connection,
    migration_file: Path,
) -> None:
    sql = migration_file.read_text(encoding="utf-8")

    async with connection.transaction():
        await connection.execute(sql)
        await connection.execute(
            "INSERT INTO schema_migrations (filename) VALUES ($1)",
            migration_file.name,
        )


async def run_migrations(
    settings: Settings | None = None,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> None:
    app_settings = settings or Settings()
    connection = await asyncpg.connect(dsn=app_settings.database_url)

    try:
        await connection.execute(CREATE_SCHEMA_MIGRATIONS_SQL)
        applied_migrations = await get_applied_migrations(connection)

        migration_files = get_migration_files(migrations_dir)

        for migration_file in migration_files:
            if migration_file.name in applied_migrations:
                print(f"Migration already applied: {migration_file.name}", flush=True)
                continue

            print(f"Applying migration: {migration_file.name}", flush=True)
            await apply_migration(connection, migration_file)
            print(f"Migration applied: {migration_file.name}", flush=True)

        print("Database migrations completed.", flush=True)
    finally:
        await connection.close()


def main() -> None:
    asyncio.run(run_migrations())


if __name__ == "__main__":
    main()
