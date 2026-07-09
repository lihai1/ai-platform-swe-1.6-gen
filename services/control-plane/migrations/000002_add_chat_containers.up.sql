-- Chat containers table for per-run container orchestration
CREATE TABLE IF NOT EXISTS app.chat_containers (
    id UUID PRIMARY KEY,
    run_id VARCHAR(255) UNIQUE NOT NULL,
    container_id VARCHAR(255),
    container_name VARCHAR(255) NOT NULL,
    repository_url TEXT NOT NULL,
    branch VARCHAR(255) DEFAULT 'main',
    status VARCHAR(50) NOT NULL DEFAULT 'creating',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    stopped_at TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chat_containers_run_id ON app.chat_containers(run_id);
CREATE INDEX IF NOT EXISTS idx_chat_containers_status ON app.chat_containers(status);
