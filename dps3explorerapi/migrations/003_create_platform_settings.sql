-- Phase 3: Platform settings table (singleton for global config)
-- Run against the shared rhymedatapoem schema

BEGIN;

CREATE TABLE IF NOT EXISTS rhymedatapoem.s3_platform_settings (
    id                  INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    allowed_extensions  JSONB NOT NULL DEFAULT '[{"ext":".parquet","color":"#10b981"},{"ext":".orc","color":"#10b981"},{"ext":".csv","color":"#10b981"},{"ext":".json","color":"#f59e0b"},{"ext":".zip","color":"#8b5cf6"},{"ext":".gz","color":"#8b5cf6"},{"ext":".xlsx","color":"#10b981"},{"ext":".txt","color":"#3b82f6"},{"ext":".pdf","color":"#3b82f6"},{"ext":".docx","color":"#3b82f6"},{"ext":".png","color":"#ec4899"}]'::jsonb,
    max_upload_bytes    BIGINT NOT NULL DEFAULT 5368709120,
    updated_by          INTEGER,
    updated_at          TIMESTAMPTZ DEFAULT now()
);

INSERT INTO rhymedatapoem.s3_platform_settings (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

COMMIT;
