CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    hashed_password TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower
    ON users (LOWER(email));

CREATE INDEX IF NOT EXISTS idx_users_created_at
    ON users (created_at);

ALTER TABLE request_history
    ADD COLUMN IF NOT EXISTS user_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_request_history_user_id'
          AND conrelid = 'request_history'::regclass
    ) THEN
        ALTER TABLE request_history
            ADD CONSTRAINT fk_request_history_user_id
            FOREIGN KEY (user_id)
            REFERENCES users (id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_request_history_user_id
    ON request_history (user_id);

CREATE INDEX IF NOT EXISTS idx_request_history_user_id_created_at
    ON request_history (user_id, created_at DESC);
