"""Database migration runner for applying ordered SQL migration files."""

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
    """Collect SQL migration files in deterministic execution order.

    Args:
        migrations_dir: Directory containing versioned SQL migration files.

    Returns:
        Sorted list of SQL files that can be applied by the runner.
    """
    return sorted(path for path in migrations_dir.glob("*.sql") if path.is_file())


async def get_applied_migrations(connection: asyncpg.Connection) -> set[str]:
    """Load names of migrations already recorded in the database.

    Args:
        connection: Open database connection used by the migration runner.

    Returns:
        Set of migration filenames stored in the schema_migrations table.
    """
    rows = await connection.fetch("SELECT filename FROM schema_migrations")
    return {row["filename"] for row in rows}


async def apply_migration(
    connection: asyncpg.Connection,
    migration_file: Path,
) -> None:
    """Apply one SQL migration and record it in the migration ledger.

    Args:
        connection: Open database connection used for the transaction.
        migration_file: SQL file to execute.

    Returns:
        None

    Raises:
        asyncpg.PostgresError: If SQL execution or ledger insertion fails.
        OSError: If the migration file cannot be read.
    """
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
    """Apply all pending SQL migrations to the configured database.

    Args:
        settings: Optional settings override for tests or operational callers.
        migrations_dir: Directory containing ordered migration files.

    Returns:
        None

    Raises:
        asyncpg.PostgresError: If the database connection or migration SQL
            fails.
        OSError: If a pending migration file cannot be read.
    """
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
    """Run database migrations from the command line entry point.

    Args:
        None

    Returns:
        None
    """
    asyncio.run(run_migrations())


if __name__ == "__main__":
    main()
