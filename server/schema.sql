-- Runs on every start; every statement must be safe to repeat.

-- No accounts: each browser gets a device with a secret token (only its hash is stored).
CREATE TABLE IF NOT EXISTS devices (
  id          text PRIMARY KEY,               -- public, used in profile links
  token_hash  text NOT NULL UNIQUE,
  name        text NOT NULL,
  banned      boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scores (
  id          text PRIMARY KEY,
  device_id   text NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  title       text NOT NULL,
  subtitle    text NOT NULL DEFAULT '',
  game        text NOT NULL,
  data        jsonb NOT NULL,                 -- notes text and editor options
  listed      boolean NOT NULL DEFAULT true,  -- false: only reachable by its link
  hidden      boolean NOT NULL DEFAULT false, -- set by reports, cleared by an admin
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS scores_device ON scores (device_id);
CREATE INDEX IF NOT EXISTS scores_created ON scores (created_at DESC);

CREATE TABLE IF NOT EXISTS votes (
  score_id    text NOT NULL REFERENCES scores(id) ON DELETE CASCADE,
  device_id   text NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (score_id, device_id)
);
CREATE INDEX IF NOT EXISTS votes_recent ON votes (created_at);

CREATE TABLE IF NOT EXISTS comments (
  id          bigserial PRIMARY KEY,
  score_id    text NOT NULL REFERENCES scores(id) ON DELETE CASCADE,
  device_id   text NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  body        text NOT NULL,
  hidden      boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS comments_score ON comments (score_id, created_at);

CREATE TABLE IF NOT EXISTS reports (
  kind        text NOT NULL CHECK (kind IN ('score', 'comment')),
  target      text NOT NULL,
  device_id   text NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  reason      text NOT NULL DEFAULT '',
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (kind, target, device_id)
);
