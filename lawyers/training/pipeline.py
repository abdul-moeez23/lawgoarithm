import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone as dj_timezone

from lawyers.models import LawyerProfile

logger = logging.getLogger(__name__)


def _artifacts_root():
    return Path(getattr(settings, "BASE_DIR")) / "artifacts" / "models"


def _get_active_model_version():
    return getattr(settings, "LEGAL_MATCHER_ACTIVE_VERSION", "base")


def _get_model_dir(version):
    return _artifacts_root() / version


def _get_model_path(version):
    return _get_model_dir(version) / "model"


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _utc_now():
    return datetime.now(timezone.utc)


def _build_lawyer_training_text(lawyer):
    practice_areas = ", ".join(pa.name for pa in lawyer.practice_areas.all()) or "Not listed"
    courts = ", ".join(c.name for c in lawyer.courts.all()) or "Not listed"
    city = lawyer.city.name if lawyer.city else "Not listed"
    display_name = lawyer.user.get_full_name() or lawyer.user.username
    return f"{display_name}. City: {city}. Practice areas: {practice_areas}. Courts: {courts}. Experience: {lawyer.experience_years} years."


def _build_case_training_text(case):
    category = case.category.name if getattr(case, "category", None) else "Not listed"
    subcategory = case.subcategory.name if getattr(case, "subcategory", None) else "Not listed"
    city = case.city.name if getattr(case, "city", None) else "Not listed"
    court = case.court_level.name if getattr(case, "court_level", None) else "Not listed"
    return f"{case.title}. {case.description}. Category: {category}. Subcategory: {subcategory}. City: {city}. Court: {court}."


def _map_interaction_outcome_to_label(status):
    return "positive" if status in {"accepted", "hired", "completed"} else "negative"


def _recall_at_k(ranked_ids, relevant_ids, k):
    if not relevant_ids:
        return 0.0
    top_k = set(ranked_ids[:k])
    return len(top_k.intersection(relevant_ids)) / len(relevant_ids)


def _reciprocal_rank(ranked_ids, relevant_ids):
    for idx, lawyer_id in enumerate(ranked_ids, start=1):
        if lawyer_id in relevant_ids:
            return 1.0 / idx
    return 0.0


def load_sentence_transformer_for_version(version=None):
    from sentence_transformers import SentenceTransformer

    base_name = getattr(settings, "LEGAL_MATCHER_BASE_MODEL", "all-MiniLM-L6-v2")
    requested_version = version or _get_active_model_version()
    model_path = _get_model_path(requested_version)
    if model_path.exists():
        return SentenceTransformer(str(model_path)), requested_version, str(model_path)
    return SentenceTransformer(base_name), "base", base_name


def refresh_lawyer_embedding(lawyer, model=None, model_version=None):
    if lawyer.verification_status != "approved":
        return False
    if model is None:
        model, resolved_version, _ = load_sentence_transformer_for_version(model_version)
        model_version = resolved_version
    text = _build_lawyer_training_text(lawyer)
    vector = model.encode([text])[0]
    normalized_vector = [float(v) for v in vector]
    lawyer.embedding_vector = normalized_vector
    lawyer.embedding_model_version = model_version or "base"
    lawyer.embedding_updated_at = dj_timezone.now()
    lawyer.save(
        update_fields=[
            "embedding_vector",
            "embedding_model_version",
            "embedding_updated_at",
        ]
    )
    return True


def refresh_all_lawyer_embeddings(model_version=None):
    model, resolved_version, _ = load_sentence_transformer_for_version(model_version)
    qs = (
        LawyerProfile.objects.filter(verification_status="approved")
        .select_related("user", "city")
        .prefetch_related("practice_areas", "courts")
    )
    total = qs.count()
    updated = 0
    failed = 0
    for lawyer in qs.iterator(chunk_size=200):
        try:
            if refresh_lawyer_embedding(lawyer, model=model, model_version=resolved_version):
                updated += 1
        except Exception:
            failed += 1
            logger.exception("Embedding refresh failed for lawyer_id=%s", lawyer.pk)
    cache.clear()
    return {
        "total": total,
        "updated": updated,
        "failed": failed,
        "model_version": resolved_version,
    }


def train_model(dataset_path, model_version, epochs=1, batch_size=16):
    from sentence_transformers import InputExample, SentenceTransformer, losses
    from torch.utils.data import DataLoader

    base_name = getattr(settings, "LEGAL_MATCHER_BASE_MODEL", "all-MiniLM-L6-v2")
    model = SentenceTransformer(base_name)
    examples = []
    with open(dataset_path, encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            examples.append(InputExample(texts=[row["anchor"], row["positive"]]))
    if not examples:
        raise ValueError(f"No training rows found in dataset: {dataset_path}")
    train_loader = DataLoader(examples, batch_size=batch_size, shuffle=True)
    train_loss = losses.MultipleNegativesRankingLoss(model)
    output_dir = _get_model_dir(model_version) / "model"
    output_dir.mkdir(parents=True, exist_ok=True)
    model.fit(train_objectives=[(train_loader, train_loss)], epochs=epochs, output_path=str(output_dir), show_progress_bar=False)
    metadata = {
        "model_version": model_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "base_model": base_name,
        "loss": "MultipleNegativesRankingLoss",
        "dataset_path": dataset_path,
        "train_examples": len(examples),
        "epochs": epochs,
        "batch_size": batch_size,
    }
    _write_json(_get_model_dir(model_version) / "metadata.json", metadata)
    return metadata


def evaluate_model(model_version, k_values=(1, 3, 5)):
    from clients.models import Case, Interaction

    model, resolved_version, _ = load_sentence_transformer_for_version(model_version)
    interactions = (
        Interaction.objects.all()
        .select_related("case", "lawyer", "lawyer__user", "lawyer__city")
        .prefetch_related("lawyer__practice_areas", "lawyer__courts")
    )
    case_to_positive = {}
    for row in interactions:
        if _map_interaction_outcome_to_label(row.status) != "positive":
            continue
        case_to_positive.setdefault(row.case_id, set()).add(row.lawyer_id)
    if not case_to_positive:
        return {"model_version": resolved_version, "queries": 0, "recall": {f"recall@{k}": 0.0 for k in k_values}, "mrr": 0.0}

    approved_lawyers = list(
        LawyerProfile.objects.filter(verification_status="approved")
        .select_related("user", "city")
        .prefetch_related("practice_areas", "courts")
    )
    lawyer_ids = [lawyer.id for lawyer in approved_lawyers]
    lawyer_texts = [_build_lawyer_training_text(lawyer) for lawyer in approved_lawyers]
    lawyer_embs = model.encode(lawyer_texts) if lawyer_texts else None

    from sklearn.metrics.pairwise import cosine_similarity

    recalls = {k: [] for k in k_values}
    mrr_scores = []
    cases = Case.objects.filter(id__in=case_to_positive.keys())
    for case in cases.iterator():
        case_emb = model.encode([_build_case_training_text(case)])[0]
        sims = cosine_similarity([case_emb], lawyer_embs)[0] if lawyer_embs is not None else []
        ranked_pairs = sorted(zip(lawyer_ids, sims), key=lambda item: item[1], reverse=True)
        ranked_ids = [lawyer_id for lawyer_id, _ in ranked_pairs]
        relevant_ids = case_to_positive.get(case.id, set())
        for k in k_values:
            recalls[k].append(_recall_at_k(ranked_ids, relevant_ids, k))
        mrr_scores.append(_reciprocal_rank(ranked_ids, relevant_ids))

    results = {
        "model_version": resolved_version,
        "queries": len(mrr_scores),
        "recall": {f"recall@{k}": (sum(values) / len(values) if values else 0.0) for k, values in recalls.items()},
        "mrr": sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0.0,
        "evaluated_at": _utc_now().isoformat(),
    }
    report_dir = _artifacts_root() / "reports" / resolved_version
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_json(report_dir / "metrics.json", results)
    md_path = report_dir / "metrics.md"
    md_path.write_text(
        "\n".join(
            [
                f"# Evaluation: {resolved_version}",
                f"- Queries: {results['queries']}",
                f"- Recall@1: {results['recall'].get('recall@1', 0.0):.4f}",
                f"- Recall@3: {results['recall'].get('recall@3', 0.0):.4f}",
                f"- Recall@5: {results['recall'].get('recall@5', 0.0):.4f}",
                f"- MRR: {results['mrr']:.4f}",
            ]
        ),
        encoding="utf-8",
    )
    return results


def run_retrain_cycle(dataset_version, model_version, dataset_exporter, promote_if_pass=False, min_mrr=0.1):
    export_summary = dataset_exporter(dataset_version)
    metadata = train_model(export_summary["triplets_jsonl"], model_version=model_version)
    metrics = evaluate_model(model_version)
    promoted = False
    if promote_if_pass and metrics.get("mrr", 0.0) >= min_mrr:
        # Keep promotion marker in settings-driven active version when registry module is absent.
        refresh_all_lawyer_embeddings(model_version)
        promoted = True
    return {
        "dataset": export_summary,
        "training": metadata,
        "metrics": metrics,
        "promoted": promoted,
    }
