import statistics
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.test.utils import override_settings

from clients.models import Case
from lawyers.models import LawyerProfile
from lawyers.services.matching import MatchingService


class Command(BaseCommand):
    help = "Validate vector matching readiness: coverage, latency, and shadow overlap."

    def add_arguments(self, parser):
        parser.add_argument("--sample-cases", type=int, default=25)
        parser.add_argument("--top-k", type=int, default=5)

    def handle(self, *args, **options):
        sample_cases = max(1, options["sample_cases"])
        top_k = max(1, options["top_k"])

        approved_total = LawyerProfile.objects.filter(verification_status="approved").count()
        approved_with_vector = LawyerProfile.objects.filter(
            verification_status="approved",
            embedding_vector__isnull=False,
        ).count()
        coverage = (approved_with_vector / approved_total) if approved_total else 0.0

        cases = list(
            Case.objects.select_related("category", "subcategory", "city", "court_level")
            .order_by("-id")[:sample_cases]
        )

        latencies_ms = []
        shadow_overlaps = []
        duplicate_score_rates = []
        score_variances = []
        stability_rates = []
        for case in cases:
            candidates = MatchingService.get_candidate_lawyers(case, getattr(settings, "MATCH_CANDIDATE_LIMIT", 30))
            if not candidates:
                continue

            start = time.perf_counter()
            vector_matches = MatchingService.get_best_matches(case, top_k=top_k)
            latencies_ms.append((time.perf_counter() - start) * 1000)

            fallback_matches = MatchingService._fallback_embedding_rank(case, candidates, top_k=top_k)
            vector_ids = {row["lawyer"].id for row in vector_matches}
            fallback_ids = {row["lawyer"].id for row in fallback_matches}
            if vector_ids or fallback_ids:
                overlap = len(vector_ids.intersection(fallback_ids)) / max(len(vector_ids.union(fallback_ids)), 1)
                shadow_overlaps.append(overlap)

            scores = [int(row.get("score", 0)) for row in vector_matches]
            if scores:
                unique_scores = len(set(scores))
                duplicate_score_rates.append(1.0 - (unique_scores / len(scores)))
                score_variances.append(statistics.pvariance(scores) if len(scores) > 1 else 0.0)

            with override_settings(MATCH_SCORE_V2_ENABLED=False):
                legacy_matches = MatchingService.get_best_matches(case, top_k=top_k)
            with override_settings(MATCH_SCORE_V2_ENABLED=True):
                v2_matches = MatchingService.get_best_matches(case, top_k=top_k)
            legacy_ids = [row["lawyer"].id for row in legacy_matches]
            v2_ids = [row["lawyer"].id for row in v2_matches]
            denom = max(len(set(legacy_ids).union(set(v2_ids))), 1)
            stability_rates.append(len(set(legacy_ids).intersection(set(v2_ids))) / denom)

        p95_ms = 0.0
        if latencies_ms:
            sorted_latencies = sorted(latencies_ms)
            idx = max(0, min(len(sorted_latencies) - 1, int(0.95 * (len(sorted_latencies) - 1))))
            p95_ms = sorted_latencies[idx]

        avg_overlap = statistics.mean(shadow_overlaps) if shadow_overlaps else 0.0
        report = {
            "approved_total": approved_total,
            "approved_with_vector": approved_with_vector,
            "embedding_coverage": round(coverage, 4),
            "sampled_cases": len(cases),
            "latency_p95_ms": round(p95_ms, 2),
            "shadow_jaccard_overlap": round(avg_overlap, 4),
            "duplicate_score_rate_avg": round(statistics.mean(duplicate_score_rates), 4) if duplicate_score_rates else 0.0,
            "score_variance_avg": round(statistics.mean(score_variances), 4) if score_variances else 0.0,
            "legacy_v2_stability_avg": round(statistics.mean(stability_rates), 4) if stability_rates else 0.0,
            "match_score_v2_enabled": bool(getattr(settings, "MATCH_SCORE_V2_ENABLED", False)),
        }
        self.stdout.write(self.style.SUCCESS(f"Vector validation report: {report}"))
