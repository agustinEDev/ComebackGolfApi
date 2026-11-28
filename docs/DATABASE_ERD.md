# 🗄️ Database Entity Relationship Diagram (ERD)

> **Version:** 2.82.2
> **Last updated:** 28 November 2026
> **Database:** PostgreSQL 15 (the image used by `docker/docker-compose.yml`, the Kind cluster and the CI integration job)

---

## Source of truth

This document is a **snapshot**. The schema lives in code:

- **SQLAlchemy imperative mappers** (`src/modules/*/infrastructure/persistence/sqlalchemy/` and `src/shared/infrastructure/persistence/sqlalchemy/`), registered on one `MetaData` in `src/shared/infrastructure/persistence/sqlalchemy/base.py`.
- **Alembic migrations** (`alembic/versions/`), which build the production schema. `alembic/env.py` uses the same `MetaData` as `target_metadata`.
- `tests/integration/test_schema_parity.py` checks that the schema built by the mappers and the one built by the migrations match.

The diagrams below were generated from that `MetaData` (**44 tables**). Column types are the PostgreSQL types SQLAlchemy compiles (`char` = fixed-length string ids, `timestamp_tz` = `timestamp with time zone`, `*_enum` = PostgreSQL enum types). Foreign keys are drawn as one-to-many; uniqueness, check constraints and indexes are not shown: read the mappers and migrations for those.

To regenerate a table list from the code:

```bash
ENVIRONMENT=development python -c "import main; from src.shared.infrastructure.persistence.sqlalchemy.base import metadata; print(sorted(metadata.tables))"
```

---

## Tables by area

| Area | Tables |
|------|--------|
| Users, sessions and accounts (user module, shared countries) | `users`, `user_devices`, `refresh_tokens`, `password_history`, `user_oauth_accounts`, `terms_acceptances`, `user_avatar_uploads`, `countries`, `country_adjacencies` |
| Competitions: setup, enrollment and teams | `competitions`, `competition_golf_courses`, `competition_course_tees`, `enrollments`, `enrollment_course_tees`, `invitations`, `team_assignments`, `drafts`, `envelopes`, `handicap_updates`, `handicap_refreshes`, `handicap_update_schedules`, `handicap_update_emails` |
| Competitions: rounds, matches and scoring | `rounds`, `matches`, `hole_scores`, `tee_groups`, `tee_group_players`, `tee_group_hole_scores`, `tee_window_places`, `tee_window_waits`, `withdrawn_tee_time_notices` |
| Golf courses and hole maps | `golf_courses`, `golf_course_tees`, `golf_course_tee_holes`, `golf_course_hole_maps`, `golf_course_hole_reports`, `golf_course_hole_samples`, `golf_course_saved_holes` |
| Quick matches and social | `quick_matches`, `quick_match_hole_scores`, `friendships`, `activity_events`, `profile_photos`, `withdrawn_hidden_achievements` |

Notes:

- **Match play** (Ryder format) scoring is stored per player and hole in `hole_scores` (match `matches`). **Stroke play** (Stableford and Medal) scores by tee group: `tee_groups` → `tee_group_players` → `tee_group_hole_scores`.
- Several aggregates keep lists as `jsonb` instead of join tables (for example `matches.team_a_players`, `team_assignments.team_a_player_ids`, `quick_matches.participants`, `drafts.picks`).
- Profile photos and uploaded avatars are stored in the database (`bytea`), not on disk.

---

## Diagrams

Tables that belong to another area appear without columns.

### Users, sessions and accounts

```mermaid
erDiagram
    users {
        char id PK
        varchar first_name
        varchar last_name
        varchar alias
        varchar email
        varchar password
        float handicap
        timestamp_tz handicap_updated_at
        timestamp created_at
        timestamp updated_at
        boolean email_verified
        varchar verification_token
        timestamp verification_token_expires_at
        varchar password_reset_token
        timestamp reset_token_expires_at
        integer password_reset_emails_in_window
        timestamp password_reset_window_started_at
        timestamp register_attempt_notice_at
        varchar pending_email
        varchar pending_email_token
        timestamp pending_email_expires_at
        char country_code FK
        integer failed_login_attempts
        timestamp locked_until
        timestamp failed_login_window_started_at
        timestamp failed_login_notice_at
        integer failed_login_day_attempts
        timestamp failed_login_day_window_started_at
        boolean is_admin
        boolean is_active
        varchar gender
        varchar avatar_source
        integer avatar_preset_id
        timestamp feed_last_seen_at
        boolean share_activity
        char active_avatar_upload_id FK
        timestamp_tz terms_accepted_at
        varchar terms_version
    }
    user_devices {
        char id PK
        char user_id FK
        varchar device_name
        text user_agent
        varchar ip_address
        varchar fingerprint_hash
        boolean is_active
        timestamp last_used_at
        timestamp created_at
        boolean installed_app
        varchar country_code
        timestamp new_login_notice_at
        timestamp_tz session_closed_at
    }
    refresh_tokens {
        varchar id PK
        char user_id FK
        varchar device_id FK
        varchar token_hash
        timestamp expires_at
        timestamp created_at
        boolean revoked
        timestamp revoked_at
        timestamp replaced_at
        varchar replaced_by_id
        timestamp annulled_at
    }
    password_history {
        char id PK
        char user_id FK
        varchar password_hash
        timestamp created_at
    }
    user_oauth_accounts {
        char id PK
        char user_id FK
        varchar provider
        varchar provider_user_id
        varchar provider_email
        timestamp created_at
    }
    terms_acceptances {
        char id PK
        char user_id FK
        varchar user_email
        varchar terms_version
        timestamp_tz accepted_at
        varchar ip_address
        varchar user_agent
        timestamp_tz user_deleted_at
    }
    user_avatar_uploads {
        char id PK
        char user_id FK
        bytea image_data
        varchar content_type
        timestamp created_at
    }
    countries {
        char code PK
        boolean active
        varchar name_en
        varchar name_es
    }
    country_adjacencies {
        char country_code_1 PK, FK
        char country_code_2 PK, FK
    }
    countries ||--o{ country_adjacencies : "country_code_1"
    countries ||--o{ country_adjacencies : "country_code_2"
    countries ||--o{ users : "country_code"
    user_avatar_uploads ||--o{ users : "active_avatar_upload_id"
    user_devices ||--o{ refresh_tokens : "device_id"
    users ||--o{ password_history : "user_id"
    users ||--o{ refresh_tokens : "user_id"
    users ||--o{ terms_acceptances : "user_id"
    users ||--o{ user_avatar_uploads : "user_id"
    users ||--o{ user_devices : "user_id"
    users ||--o{ user_oauth_accounts : "user_id"
```

### Competitions: setup, enrollment and teams

```mermaid
erDiagram
    competitions {
        char id PK
        char creator_id FK
        varchar name
        date start_date
        date end_date
        char country_code FK
        char secondary_country_code FK
        char tertiary_country_code FK
        varchar team_1_name
        varchar team_2_name
        varchar play_mode
        integer max_players
        varchar team_assignment
        varchar status
        integer max_playing_handicap
        integer enrollment_opens_days_before
        timestamp enrollment_opened_at
        boolean enrollment_closed_by_deadline
        boolean enrollment_close_blocked_notified
        varchar visibility
        varchar setup_mode
        varchar tournament_type
        numeric_array stroke_category_limits
        integer stroke_max_matchdays_per_player
        varchar stroke_overall_standing
        integer stroke_category_count
        char team_a_captain_id FK
        char team_b_captain_id FK
        char team_a_vice_captain_id FK
        char team_b_vice_captain_id FK
        timestamp created_at
        timestamp updated_at
    }
    competition_golf_courses {
        char id PK
        char competition_id FK
        uuid golf_course_id FK
        integer display_order
        timestamp created_at
    }
    competition_course_tees {
        char competition_id PK, FK
        uuid golf_course_id PK, FK
        varchar gender PK
        varchar tee_color
        timestamp_tz updated_at
    }
    enrollments {
        char id PK
        char competition_id FK
        char user_id FK
        varchar status
        varchar team_id
        numeric custom_handicap
        varchar tee_color
        boolean use_real_name
        numeric fixed_handicap
        integer fixed_category
        boolean entered_waiting
        timestamp created_at
        timestamp updated_at
    }
    enrollment_course_tees {
        char enrollment_id PK, FK
        uuid golf_course_id PK, FK
        varchar tee_color
        timestamp_tz updated_at
    }
    invitations {
        char id PK
        char competition_id FK
        char inviter_id FK
        varchar invitee_email
        char invitee_user_id FK
        varchar status
        text personal_message
        timestamp expires_at
        timestamp responded_at
        timestamp created_at
        timestamp updated_at
        boolean sent_by_email
    }
    team_assignments {
        char id PK
        char competition_id FK
        varchar mode
        jsonb team_a_player_ids
        jsonb team_b_player_ids
        timestamp created_at
    }
    drafts {
        char id PK
        char competition_id FK
        char team_a_captain_id FK
        char team_b_captain_id FK
        varchar status
        varchar first_pick
        varchar current_team
        timestamp turn_started_at
        jsonb picks
        integer seconds_per_turn
    }
    envelopes {
        char id PK
        char competition_id FK
        char round_id FK
        varchar team
        varchar match_format
        jsonb entries
        timestamp submitted_at
        char submitted_by FK
        boolean automatic
        boolean revealed
        boolean reveal_when_both_ready
    }
    handicap_updates {
        char id PK
        char competition_id FK
        varchar origin
        varchar status
        timestamp_tz created_at
        timestamp_tz finished_at
        timestamp_tz resumed_at
    }
    handicap_refreshes {
        char update_id PK, FK
        char user_id PK, FK
        varchar result
        integer attempts
        timestamp_tz refreshed_at
    }
    handicap_update_schedules {
        char competition_id PK, FK
        timestamp_tz run_at
        timestamp_tz created_at
    }
    handicap_update_emails {
        char competition_id PK, FK
        char user_id PK, FK
        varchar kind PK
        varchar fingerprint
        timestamp_tz sent_at
    }
    competitions ||--o{ competition_course_tees : "competition_id"
    competitions ||--o{ competition_golf_courses : "competition_id"
    competitions ||--o{ drafts : "competition_id"
    competitions ||--o{ enrollments : "competition_id"
    competitions ||--o{ envelopes : "competition_id"
    competitions ||--o{ handicap_update_emails : "competition_id"
    competitions ||--o{ handicap_update_schedules : "competition_id"
    competitions ||--o{ handicap_updates : "competition_id"
    competitions ||--o{ invitations : "competition_id"
    competitions ||--o{ team_assignments : "competition_id"
    countries ||--o{ competitions : "country_code"
    countries ||--o{ competitions : "secondary_country_code"
    countries ||--o{ competitions : "tertiary_country_code"
    enrollments ||--o{ enrollment_course_tees : "enrollment_id"
    golf_courses ||--o{ competition_course_tees : "golf_course_id"
    golf_courses ||--o{ competition_golf_courses : "golf_course_id"
    golf_courses ||--o{ enrollment_course_tees : "golf_course_id"
    handicap_updates ||--o{ handicap_refreshes : "update_id"
    rounds ||--o{ envelopes : "round_id"
    users ||--o{ competitions : "creator_id"
    users ||--o{ competitions : "team_a_captain_id"
    users ||--o{ competitions : "team_a_vice_captain_id"
    users ||--o{ competitions : "team_b_captain_id"
    users ||--o{ competitions : "team_b_vice_captain_id"
    users ||--o{ drafts : "team_a_captain_id"
    users ||--o{ drafts : "team_b_captain_id"
    users ||--o{ enrollments : "user_id"
    users ||--o{ envelopes : "submitted_by"
    users ||--o{ handicap_refreshes : "user_id"
    users ||--o{ handicap_update_emails : "user_id"
    users ||--o{ invitations : "invitee_user_id"
    users ||--o{ invitations : "inviter_id"
```

### Competitions: rounds, matches and scoring

```mermaid
erDiagram
    rounds {
        char id PK
        char competition_id FK
        uuid golf_course_id FK
        date round_date
        varchar session_type
        varchar match_format
        varchar status
        varchar handicap_mode
        integer allowance_percentage
        timestamp created_at
        timestamp updated_at
        jsonb match_generation_block
        jsonb tee_sheet
    }
    matches {
        char id PK
        char round_id FK
        integer match_number
        jsonb team_a_players
        jsonb team_b_players
        varchar status
        integer handicap_strokes_given
        varchar strokes_given_to_team
        jsonb result
        jsonb marker_assignments
        jsonb scorecard_submitted_by
        jsonb withdrawn_player_ids
        jsonb holes_without_ball
        boolean is_decided
        jsonb decided_result
        timestamp created_at
        timestamp updated_at
    }
    hole_scores {
        char id PK
        char match_id FK
        integer hole_number
        char player_user_id FK
        varchar team
        integer own_score
        boolean own_submitted
        integer marker_score
        boolean marker_submitted
        integer strokes_received
        integer net_score
        varchar validation_status
        timestamp created_at
        timestamp updated_at
    }
    tee_groups {
        char id PK
        char competition_id FK
        char round_id FK
        integer number
        varchar status
        timestamp_tz created_at
        timestamp_tz updated_at
    }
    tee_group_players {
        char group_id PK, FK
        char round_id FK
        char user_id PK, FK
        integer position
        numeric handicap_index
        integer playing_handicap
        varchar tee_color
        varchar tee_gender
        jsonb strokes_by_hole
        jsonb pars_by_hole
        varchar card_status
        char marks_user_id FK
        boolean brought_in
        boolean played
    }
    tee_group_hole_scores {
        char group_id PK, FK
        char user_id PK, FK
        integer hole_number PK
        char round_id
        char competition_id
        integer own_score
        boolean own_submitted
        char own_by
        integer marker_score
        boolean marker_submitted
        char marker_by
        timestamp_tz created_at
        timestamp_tz updated_at
    }
    tee_window_places {
        char id PK
        char competition_id FK
        char round_id FK
        char user_id FK
        timestamp_tz created_at
        timestamp_tz from_waiting_list_at
        timestamp_tz acknowledged_at
    }
    tee_window_waits {
        char id PK
        char competition_id FK
        char round_id FK
        char user_id FK
        timestamp_tz created_at
    }
    withdrawn_tee_time_notices {
        char user_id PK, FK
        varchar round_id PK
        varchar competition_id
        timestamp withdrawn_at
    }
    competitions ||--o{ rounds : "competition_id"
    competitions ||--o{ tee_groups : "competition_id"
    competitions ||--o{ tee_window_places : "competition_id"
    competitions ||--o{ tee_window_waits : "competition_id"
    golf_courses ||--o{ rounds : "golf_course_id"
    matches ||--o{ hole_scores : "match_id"
    rounds ||--o{ matches : "round_id"
    rounds ||--o{ tee_groups : "round_id"
    rounds ||--o{ tee_window_places : "round_id"
    rounds ||--o{ tee_window_waits : "round_id"
    tee_group_players ||--o{ tee_group_hole_scores : "group_id"
    tee_group_players ||--o{ tee_group_hole_scores : "user_id"
    tee_groups ||--o{ tee_group_players : "group_id"
    tee_groups ||--o{ tee_group_players : "round_id"
    users ||--o{ hole_scores : "player_user_id"
    users ||--o{ tee_group_players : "marks_user_id"
    users ||--o{ tee_group_players : "user_id"
    users ||--o{ tee_window_places : "user_id"
    users ||--o{ tee_window_waits : "user_id"
    users ||--o{ withdrawn_tee_time_notices : "user_id"
```

### Golf courses and hole maps

```mermaid
erDiagram
    golf_courses {
        uuid id PK
        varchar name
        varchar country_code FK
        course_type_enum course_type
        char creator_id FK
        approval_status_enum approval_status
        varchar rejection_reason
        timestamp created_at
        timestamp updated_at
        uuid original_golf_course_id FK
        boolean is_pending_update
        float latitude
        float longitude
        varchar address
        varchar city
        varchar province
        varchar timezone
        course_source_enum source
        varchar external_id
        timestamp imported_at
        integer physical_holes
    }
    golf_course_tees {
        integer id PK
        uuid golf_course_id FK
        varchar tee_gender
        tee_color_enum color
        varchar identifier
        float course_rating
        integer slope_rating
    }
    golf_course_tee_holes {
        integer id PK
        integer tee_id FK
        integer hole_number
        integer par
        integer stroke_index
        integer meters
    }
    golf_course_hole_maps {
        uuid golf_course_id PK, FK
        jsonb holes
        varchar osm_reference
        timestamp imported_at
        varchar status
        char reviewed_by FK
        timestamp reviewed_at
        varchar rejection_reason
        timestamp created_at
        timestamp updated_at
    }
    golf_course_hole_reports {
        uuid id PK
        bigint seq
        uuid golf_course_id FK
        smallint hole_number
        varchar reason
        float tee_latitude
        float tee_longitude
        jsonb bends
        float green_latitude
        float green_longitude
        date received_on
    }
    golf_course_hole_samples {
        uuid id PK
        bigint seq
        uuid golf_course_id FK
        smallint hole_number
        tee_color_enum tee_color
        varchar tee_gender
        float tee_latitude
        float tee_longitude
        jsonb bends
        float green_latitude
        float green_longitude
        date received_on
    }
    golf_course_saved_holes {
        uuid golf_course_id PK, FK
        smallint hole_number PK
        float tee_latitude
        float tee_longitude
        jsonb bends
        float green_latitude
        float green_longitude
        char saved_by FK
        timestamp saved_at
    }
    countries ||--o{ golf_courses : "country_code"
    golf_course_tees ||--o{ golf_course_tee_holes : "tee_id"
    golf_courses ||--o{ golf_course_hole_maps : "golf_course_id"
    golf_courses ||--o{ golf_course_hole_reports : "golf_course_id"
    golf_courses ||--o{ golf_course_hole_samples : "golf_course_id"
    golf_courses ||--o{ golf_course_saved_holes : "golf_course_id"
    golf_courses ||--o{ golf_course_tees : "golf_course_id"
    golf_courses ||--o{ golf_courses : "original_golf_course_id"
    users ||--o{ golf_course_hole_maps : "reviewed_by"
    users ||--o{ golf_course_saved_holes : "saved_by"
    users ||--o{ golf_courses : "creator_id"
```

### Quick matches and social

```mermaid
erDiagram
    quick_matches {
        uuid id PK
        char creator_id FK
        uuid golf_course_id FK
        varchar match_format
        varchar scoring_format
        varchar status
        varchar name
        integer allowance_percentage
        varchar play_mode
        jsonb participants
        jsonb scorer_ids
        jsonb hidden_by_participant_ids
        jsonb stats_excluded_by_participant_ids
        timestamp created_at
        timestamp updated_at
        timestamp started_at
    }
    quick_match_hole_scores {
        uuid id PK
        uuid quick_match_id FK
        integer hole_number
        uuid participant_id
        integer score
        uuid recorded_by_participant_id
        timestamp created_at
        timestamp updated_at
    }
    friendships {
        char id PK
        char requester_id FK
        char addressee_id FK
        varchar status
        char blocked_by FK
        timestamp responded_at
        timestamp created_at
        timestamp updated_at
        timestamp second_blocked_at
    }
    activity_events {
        uuid id PK
        char user_id FK
        varchar type
        timestamp occurred_at
        timestamp published_at
        boolean visible_to_friends
        timestamp written_at
        jsonb payload
        varchar source_match_id
    }
    profile_photos {
        uuid id PK
        char user_id FK
        bytea image_data
        varchar content_type
        varchar caption
        timestamp created_at
    }
    withdrawn_hidden_achievements {
        char user_id PK, FK
        varchar source_match_id PK
        varchar type PK
        timestamp withdrawn_at
        timestamp published_at
        boolean hidden
        jsonb hidden_holes
        varchar golf_course_id
    }
    golf_courses ||--o{ quick_matches : "golf_course_id"
    quick_matches ||--o{ quick_match_hole_scores : "quick_match_id"
    users ||--o{ activity_events : "user_id"
    users ||--o{ friendships : "addressee_id"
    users ||--o{ friendships : "blocked_by"
    users ||--o{ friendships : "requester_id"
    users ||--o{ profile_photos : "user_id"
    users ||--o{ quick_matches : "creator_id"
    users ||--o{ withdrawn_hidden_achievements : "user_id"
```

---

## 🔗 References

- [ADR-005: Repository pattern](architecture/decisions/ADR-005-repository-pattern.md)
- [ADR-010: Alembic for database migrations](architecture/decisions/ADR-010-alembic-for-database-migrations.md)
- [ADR-018: Automated database migrations in production](architecture/decisions/ADR-018-automated-database-migrations.md)
- [ADR-037: Two-tier handicap architecture and session-based round model](architecture/decisions/ADR-037-two-tier-handicap-session-round-model.md)
