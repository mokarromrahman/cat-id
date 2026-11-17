-- Gold: one table per question, built from silver. Rebuilt on every pipeline update.
-- Local dates are Edmonton days (see setup.sql for the time zone check). Rows removed from
-- Postgres (is_deleted) and soft-deleted rows (deleted_on) are left out.

-- Litterbox visits and coughs per cat per day (and per box, for visits).
CREATE OR REFRESH MATERIALIZED VIEW cat_id.gold.cat_events_daily
COMMENT 'Events per Edmonton day, cat, event type and litterbox'
AS SELECT
  to_date(from_utc_timestamp(e.event_timestamp, 'America/Edmonton')) AS event_date,
  c.name AS cat,
  et.type AS event_type,
  l.name AS location,
  count(*) AS events
FROM cat_id.silver.event e
JOIN cat_id.silver.cat c ON c.id = e.cat_id
JOIN cat_id.silver.event_type et ON et.id = e.event_type_id
LEFT JOIN cat_id.silver.location l ON l.id = e.location_id
WHERE NOT e.is_deleted
GROUP BY ALL;

-- Litterbox cleanings and bag changes per box per day.
CREATE OR REFRESH MATERIALIZED VIEW cat_id.gold.litterbox_cleanings_daily
COMMENT 'Cleanings and bag changes per Edmonton day and litterbox'
AS SELECT
  to_date(from_utc_timestamp(x.event_timestamp, 'America/Edmonton')) AS clean_date,
  l.name AS location,
  count(*) AS cleanings,
  count_if(x.bag_changed) AS bag_changes
FROM cat_id.silver.litterbox_clean_event x
JOIN cat_id.silver.location l ON l.id = x.location_id
WHERE NOT x.is_deleted
GROUP BY ALL;

-- Vet visits and pickups, one row per visit, with the cat's name (null for pickups).
CREATE OR REFRESH MATERIALIZED VIEW cat_id.gold.vet_visits
COMMENT 'Vet visits (not deleted) with cat name, weight and cost'
AS SELECT
  v.id AS vet_visit_id,
  v.visit_date,
  c.name AS cat,
  v.clinic,
  v.doctor,
  v.reason,
  v.weight_kg,
  v.cost,
  v.follow_up_date,
  v.notes
FROM cat_id.silver.vet_visit v
LEFT JOIN cat_id.silver.cat c ON c.id = v.cat_id
WHERE v.deleted_on IS NULL AND NOT v.is_deleted;

-- Every chore done, who did it and how long it took.
CREATE OR REFRESH MATERIALIZED VIEW cat_id.gold.chores_done
COMMENT 'Chores done (not deleted) with doers and minutes taken'
AS SELECT
  ce.id AS chore_event_id,
  ch.label_name AS chore,
  ce.event_timestamp AS done_at,
  to_date(from_utc_timestamp(ce.event_timestamp, 'America/Edmonton')) AS done_date,
  ce.started_on,
  round((unix_timestamp(ce.event_timestamp) - unix_timestamp(ce.started_on)) / 60, 1) AS took_minutes,
  d.done_by,
  ce.notes
FROM cat_id.silver.chore_event ce
JOIN cat_id.silver.chore ch ON ch.id = ce.chore_id
LEFT JOIN (
  SELECT ced.chore_event_id, array_sort(collect_list(u.name)) AS done_by
  FROM cat_id.silver.chore_event_doer ced
  JOIN cat_id.silver.app_user u ON u.id = ced.app_user_id
  WHERE NOT ced.is_deleted
  GROUP BY ced.chore_event_id
) d ON d.chore_event_id = ce.id
WHERE ce.deleted_on IS NULL AND NOT ce.is_deleted;
