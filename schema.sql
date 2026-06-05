CREATE TABLE IF NOT EXISTS participant_profiles (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  survey_json JSONB NOT NULL,
  setup_json JSONB NOT NULL,
  age_band TEXT,
  education TEXT,
  industry TEXT,
  occupation TEXT,
  player_wfh TEXT,
  partner_wfh TEXT,
  partner_commute TEXT,
  children_status TEXT,
  att_father TEXT,
  att_stigma TEXT,
  att_hours TEXT,
  survey_duration_ms INTEGER,
  build_version TEXT
);

CREATE TABLE IF NOT EXISTS play_sessions (
  id BIGSERIAL PRIMARY KEY,
  profile_id BIGINT REFERENCES participant_profiles(id) ON DELETE SET NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  scenario_type TEXT NOT NULL,
  build_version TEXT,
  ending_id TEXT,
  ending_title TEXT,
  failed BOOLEAN DEFAULT FALSE,
  story_state_json JSONB DEFAULT '{}'::jsonb,
  final_meters_json JSONB DEFAULT '{}'::jsonb,
  choices_json JSONB DEFAULT '[]'::jsonb,
  meter_history_json JSONB DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS scene_events (
  id BIGSERIAL PRIMARY KEY,
  session_id BIGINT NOT NULL REFERENCES play_sessions(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  scenario_type TEXT NOT NULL,
  scene_id TEXT NOT NULL,
  choice_id TEXT NOT NULL,
  response_time_ms INTEGER,
  scene_shown_at TIMESTAMPTZ,
  choice_submitted_at TIMESTAMPTZ,
  meters_before_json JSONB DEFAULT '{}'::jsonb,
  meters_after_json JSONB DEFAULT '{}'::jsonb,
  story_state_json JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS post_surveys (
  id BIGSERIAL PRIMARY KEY,
  session_id BIGINT NOT NULL UNIQUE REFERENCES play_sessions(id) ON DELETE CASCADE,
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  post_survey_json JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_play_sessions_profile_id ON play_sessions(profile_id);
CREATE INDEX IF NOT EXISTS idx_play_sessions_scenario_type ON play_sessions(scenario_type);
CREATE INDEX IF NOT EXISTS idx_scene_events_session_id ON scene_events(session_id);
CREATE INDEX IF NOT EXISTS idx_scene_events_scene_id ON scene_events(scene_id);
