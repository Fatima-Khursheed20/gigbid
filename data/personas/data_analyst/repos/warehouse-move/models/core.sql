WITH cohorts AS (SELECT
{{ config(materialized='incremental') }}
