# Pgvector Operations Runbook

## Purpose
Operational guidance for lawyer embedding lifecycle, model version changes, and rollback safety.

## Daily Health Checks
- Run `python manage.py validate_vector_matching --sample-cases 25 --top-k 5`
- Verify embedding coverage stays high for approved lawyers.
- Track p95 retrieval latency and shadow overlap trend.

## Embedding Refresh
- Single lawyer: `python manage.py refresh_lawyer_embeddings --lawyer-id <id>`
- Full refresh after profile/import changes: `python manage.py refresh_lawyer_embeddings`
- Model-specific refresh: `python manage.py refresh_lawyer_embeddings --model-version <version>`

## Model Evaluation and Promotion
- Evaluate: `python manage.py evaluate_legal_matcher --model-version <version>`
- Retrain cycle: `python manage.py run_retrain_cycle ...`
- Promote only when MRR and Recall@K exceed current production baseline.

## Auto-Embedding Triggers
- New approved lawyer profile creation.
- Updates to embedding-relevant lawyer fields.
- Practice area/court relationship changes.
- Trigger logic is registered via `lawyers.apps.LawyersConfig.ready()`.

## Rollback
- If vector retrieval quality drops, revert matching service to fallback ranking path.
- Keep model artifacts for previous stable version and reset active model pointer.
- Re-run `refresh_lawyer_embeddings` for the stable model version.
