import json
import logging
import re
import time

from django.conf import settings
from django.db.models import Avg, Count, Q

logger = logging.getLogger(__name__)


class MatchingService:
    _model = None
    _gemini_model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                cls._model = SentenceTransformer("all-MiniLM-L6-v2")
            except (ImportError, RuntimeError) as exc:
                logger.warning("Embedding model unavailable: %s", exc)
                return None
        return cls._model

    @classmethod
    def get_gemini_model(cls):
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            return None

        if cls._gemini_model is None:
            try:
                import google.generativeai as genai

                genai.configure(api_key=api_key)
                cls._gemini_model = genai.GenerativeModel(settings.GEMINI_MODEL)
            except ImportError as exc:
                logger.warning("Gemini SDK unavailable: %s", exc)
                return None
        return cls._gemini_model

    @staticmethod
    def preprocess_text(text):
        if not text:
            return ""
        return re.sub(r"\s+", " ", str(text)).strip()

    @staticmethod
    def _display_name(value):
        return getattr(value, "name", "") if value else ""

    @staticmethod
    def _strip_json_fence(content):
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        return cleaned.strip()

    @classmethod
    def build_case_prompt_block(cls, case):
        return cls.preprocess_text(
            "\n".join(
                [
                    f"Title: {case.title}",
                    f"Description: {case.description}",
                    f"Category: {cls._display_name(case.category)}",
                    f"Subcategory: {cls._display_name(case.subcategory)}",
                    f"City: {cls._display_name(case.city)}",
                    f"Court: {cls._display_name(case.court_level)}",
                    f"Urgency: {case.urgency or 'Not provided'}",
                ]
            )
        )

    @classmethod
    def get_lawyer_embedding_text(cls, lawyer):
        practice_areas = ", ".join(pa.name for pa in lawyer.practice_areas.all()) or "Not listed"
        courts = ", ".join(c.name for c in lawyer.courts.all()) or "Not listed"
        city = lawyer.city.name if lawyer.city else "Not listed"
        display_name = lawyer.user.get_full_name() or lawyer.user.username
        return cls.preprocess_text(
            (
                f"Lawyer: {display_name}. "
                f"City: {city}. "
                f"Practice areas: {practice_areas}. "
                f"Courts: {courts}. "
                f"Experience years: {lawyer.experience_years}."
            )
        )

    @staticmethod
    def _get_score_weights():
        default = {
            "semantic": 0.58,
            "subcategory": 0.10,
            "court": 0.07,
            "city": 0.06,
            "experience": 0.03,
            "success_rate": 0.09,
            "review_quality": 0.05,
            "review_confidence": 0.02,
        }
        configured = getattr(settings, "MATCH_SCORE_WEIGHTS", default)
        if not isinstance(configured, dict):
            return default
        merged = {}
        for key, fallback in default.items():
            try:
                merged[key] = float(configured.get(key, fallback))
            except (TypeError, ValueError):
                merged[key] = fallback
        total = sum(max(v, 0.0) for v in merged.values())
        if total <= 0:
            return default
        # Normalize to keep stable even if settings sum != 1.
        return {k: max(v, 0.0) / total for k, v in merged.items()}

    @staticmethod
    def _get_score_bounds():
        score_min = int(getattr(settings, "MATCH_SCORE_MIN", 50))
        score_max = int(getattr(settings, "MATCH_SCORE_MAX", 92))
        if score_min > score_max:
            score_min, score_max = score_max, score_min
        return score_min, score_max

    @classmethod
    def _compute_hybrid_components(cls, case, lawyer, semantic_similarity):
        practice_areas = list(lawyer.practice_areas.all())
        courts = list(lawyer.courts.all())
        has_subcategory = bool(case.subcategory and case.subcategory in practice_areas)
        has_court = bool(case.court_level and case.court_level in courts)
        has_city = bool(case.city and lawyer.city_id == case.city_id)
        experience_norm = min(max(float(lawyer.experience_years) / 20.0, 0.0), 1.0)
        # Similarity can be in [-1, 1]; map to [0, 1] for blending.
        semantic_norm = min(max((float(semantic_similarity) + 1.0) / 2.0, 0.0), 1.0)
        quality = getattr(lawyer, "_quality_signals", {}) or {}
        return {
            "semantic": semantic_norm,
            "subcategory": 1.0 if has_subcategory else 0.0,
            "court": 1.0 if has_court else 0.0,
            "city": 1.0 if has_city else 0.0,
            "experience": experience_norm,
            "success_rate": float(quality.get("success_rate", 0.5)),
            "review_quality": float(quality.get("review_quality", 0.75)),
            "review_confidence": float(quality.get("review_confidence", 0.0)),
        }

    @classmethod
    def _blend_hybrid_score(cls, components):
        weights = cls._get_score_weights()
        return sum(components.get(key, 0.0) * weights.get(key, 0.0) for key in weights.keys())

    @classmethod
    def _calibrate_display_scores(cls, score_rows):
        if not score_rows:
            return score_rows
        mode = str(getattr(settings, "MATCH_SCORE_CALIBRATION_MODE", "minmax")).lower().strip()
        score_min, score_max = cls._get_score_bounds()
        raws = [float(row["raw_score"]) for row in score_rows]
        min_raw, max_raw = min(raws), max(raws)

        if mode == "percentile":
            ordered = sorted((row["raw_score"], idx) for idx, row in enumerate(score_rows))
            ranks = [0] * len(score_rows)
            for rank, (_, idx) in enumerate(ordered):
                ranks[idx] = rank
            denom = max(len(score_rows) - 1, 1)
            for idx, row in enumerate(score_rows):
                frac = ranks[idx] / denom
                row["score"] = int(round(score_min + frac * (score_max - score_min)))
            return score_rows

        # Default min-max calibration
        spread = max_raw - min_raw
        if spread <= 1e-12:
            midpoint = int(round((score_min + score_max) / 2))
            for row in score_rows:
                row["score"] = midpoint
            return score_rows
        for row in score_rows:
            frac = (float(row["raw_score"]) - min_raw) / spread
            row["score"] = int(round(score_min + frac * (score_max - score_min)))
        return score_rows

    @classmethod
    def _apply_hybrid_scores(cls, case, scored_candidates, top_k):
        if not scored_candidates:
            return []
        cls._attach_lawyer_quality_signals([item["lawyer"] for item in scored_candidates])
        rows = []
        for item in scored_candidates:
            sim = float(item.get("_similarity", -1.0))
            components = cls._compute_hybrid_components(case, item["lawyer"], sim)
            raw_score = cls._blend_hybrid_score(components)
            item["_score_components"] = components
            item["raw_score"] = raw_score
            rows.append(item)
        rows = cls._calibrate_display_scores(rows)
        rows.sort(
            key=lambda item: (
                float(item.get("raw_score", 0.0)),
                float(item.get("_similarity", -1.0)),
                item["lawyer"].experience_years,
            ),
            reverse=True,
        )
        selected = rows[:top_k]
        duplicate_rate = 0.0
        if selected:
            unique_scores = len({row.get("score") for row in selected})
            duplicate_rate = 1.0 - (unique_scores / len(selected))
        logger.info(
            "match_score_v2_summary case_id=%s top_k=%s duplicate_score_rate=%.3f",
            getattr(case, "id", None),
            top_k,
            duplicate_rate,
        )
        for row in selected:
            logger.info(
                "match_score_v2_detail case_id=%s lawyer_id=%s score=%s raw=%.4f components=%s",
                getattr(case, "id", None),
                row["lawyer"].id,
                row.get("score"),
                float(row.get("raw_score", 0.0)),
                row.get("_score_components", {}),
            )
            row.pop("raw_score", None)
            row.pop("_score_components", None)
        return selected

    @classmethod
    def _attach_lawyer_quality_signals(cls, lawyers):
        if not lawyers:
            return
        try:
            from clients.models import Interaction, Rating
        except Exception:
            for lawyer in lawyers:
                lawyer._quality_signals = {"success_rate": 0.5, "review_quality": 0.75, "review_confidence": 0.0}
            return

        lawyer_ids = [lawyer.id for lawyer in lawyers]
        interaction_rows = (
            Interaction.objects.filter(lawyer_id__in=lawyer_ids)
            .values("lawyer_id")
            .annotate(
                total_interactions=Count("id"),
                successful_interactions=Count("id", filter=Q(status__in=["accepted", "hired"])),
            )
        )
        rating_rows = (
            Rating.objects.filter(interaction__lawyer_id__in=lawyer_ids)
            .values("interaction__lawyer_id")
            .annotate(avg_stars=Avg("stars"), review_count=Count("id"))
        )
        by_lawyer = {}
        for row in interaction_rows:
            total = int(row.get("total_interactions") or 0)
            success = int(row.get("successful_interactions") or 0)
            # Neutral default to avoid unfairly depressing brand-new lawyers.
            success_rate = (success / total) if total > 0 else 0.5
            by_lawyer[row["lawyer_id"]] = {
                "success_rate": min(max(success_rate, 0.0), 1.0),
                "interaction_total": total,
            }
        prior_review = float(getattr(settings, "MATCH_REVIEW_PRIOR", 0.75))
        review_bayes_m = float(getattr(settings, "MATCH_REVIEW_BAYES_M", 8.0))
        success_bayes_m = float(getattr(settings, "MATCH_SUCCESS_BAYES_M", 12.0))
        confidence_cap = float(getattr(settings, "MATCH_REVIEW_CONFIDENCE_CAP", 0.70))
        confidence_cap = min(max(confidence_cap, 0.0), 1.0)
        for row in rating_rows:
            lawyer_id = row["interaction__lawyer_id"]
            avg = float(row.get("avg_stars") or 0.0) / 5.0
            count = int(row.get("review_count") or 0)
            confidence = count / (count + review_bayes_m) if (count + review_bayes_m) > 0 else 0.0
            confidence = min(confidence, confidence_cap)
            blended_review = (confidence * avg) + ((1.0 - confidence) * prior_review)
            entry = by_lawyer.setdefault(lawyer_id, {})
            entry["review_quality"] = min(max(blended_review, 0.0), 1.0)
            entry["review_confidence"] = min(max(confidence, 0.0), 1.0)

        for lawyer in lawyers:
            defaults = by_lawyer.get(lawyer.id, {})
            # Smooth success rate toward a neutral prior to protect cold-start lawyers.
            interaction_total = int(defaults.get("interaction_total", 0))
            raw_success = float(defaults.get("success_rate", 0.5))
            success_confidence = interaction_total / (interaction_total + success_bayes_m) if (interaction_total + success_bayes_m) > 0 else 0.0
            smoothed_success = (success_confidence * raw_success) + ((1.0 - success_confidence) * 0.5)
            lawyer._quality_signals = {
                "success_rate": float(smoothed_success),
                "review_quality": float(defaults.get("review_quality", prior_review)),
                "review_confidence": float(defaults.get("review_confidence", 0.0)),
            }

    @classmethod
    def build_lawyer_summaries(cls, candidates):
        blocks = []
        for lawyer in candidates:
            practice_areas = ", ".join(pa.name for pa in lawyer.practice_areas.all()) or "Not listed"
            courts = ", ".join(c.name for c in lawyer.courts.all()) or "Not listed"
            city = lawyer.city.name if lawyer.city else "Not listed"
            display_name = lawyer.user.get_full_name() or lawyer.user.username
            blocks.append(
                "\n".join(
                    [
                        f"Lawyer ID: {lawyer.id}",
                        f"Name: {display_name}",
                        f"City: {city}",
                        f"Practice areas: {practice_areas}",
                        f"Courts: {courts}",
                        f"Experience years: {lawyer.experience_years}",
                    ]
                )
            )
        return "\n\n".join(blocks)

    @classmethod
    def get_candidate_lawyers(cls, case, limit=None):
        from lawyers.models import LawyerProfile

        limit = limit or getattr(settings, "MATCH_CANDIDATE_LIMIT", 30)
        base_queryset = (
            LawyerProfile.objects.filter(verification_status="approved")
            .select_related("user", "city")
            .prefetch_related("practice_areas", "courts")
            .distinct()
        )
        if not base_queryset.exists():
            return []

        filters = []
        if case.subcategory and case.city and case.court_level:
            filters.append(Q(practice_areas=case.subcategory) & Q(city=case.city) & Q(courts=case.court_level))
        if case.subcategory and case.city:
            filters.append(Q(practice_areas=case.subcategory) & Q(city=case.city))
        if case.subcategory and case.court_level:
            filters.append(Q(practice_areas=case.subcategory) & Q(courts=case.court_level))
        if case.subcategory:
            filters.append(Q(practice_areas=case.subcategory))
        if case.city:
            filters.append(Q(city=case.city))
        if case.court_level:
            filters.append(Q(courts=case.court_level))

        selected = []
        seen_ids = set()
        for condition in filters:
            for lawyer in base_queryset.filter(condition).distinct()[:limit]:
                if lawyer.id in seen_ids:
                    continue
                selected.append(lawyer)
                seen_ids.add(lawyer.id)
                if len(selected) >= limit:
                    return selected[:limit]

        if len(selected) < limit:
            for lawyer in base_queryset.exclude(id__in=seen_ids)[: limit - len(selected)]:
                selected.append(lawyer)

        return selected[:limit]

    @classmethod
    def _build_default_reasons(cls, case, lawyer):
        reasons = []
        practice_areas = list(lawyer.practice_areas.all())
        courts = list(lawyer.courts.all())
        if case.subcategory and case.subcategory in practice_areas:
            reasons.append(f"Handles {case.subcategory.name} matters")
        if case.city and lawyer.city == case.city:
            reasons.append(f"Based in {case.city.name}")
        if case.court_level and case.court_level in courts:
            reasons.append(f"Practices in {case.court_level.name}")
        if lawyer.experience_years:
            reasons.append(f"{lawyer.experience_years} years of experience")
        return reasons[:3] or ["Relevant legal background for this case"]

    @classmethod
    def _compute_embedding_similarities(cls, case, candidates):
        try:
            from pgvector.django import CosineDistance
        except (ImportError, RuntimeError) as exc:
            logger.warning("Embedding dependencies unavailable: %s", exc)
            return None

        model = cls.get_model()
        if model is None or not candidates:
            return None

        from lawyers.models import LawyerProfile

        case_embedding = [float(v) for v in model.encode([cls.build_case_prompt_block(case)])[0]]
        candidate_ids = [lawyer.id for lawyer in candidates]
        distances = {
            lawyer_id: float(distance)
            for lawyer_id, distance in LawyerProfile.objects.filter(
                id__in=candidate_ids,
                embedding_vector__isnull=False,
            )
            .annotate(distance=CosineDistance("embedding_vector", case_embedding))
            .values_list("id", "distance")
        }
        if not distances:
            return None

        similarities = []
        for lawyer in candidates:
            distance = distances.get(lawyer.id)
            if distance is None:
                similarities.append(None)
                continue
            # CosineDistance is (1 - cosine_similarity) so convert back for scoring.
            similarities.append(1.0 - distance)
        return similarities

    @classmethod
    def _fallback_embedding_rank(cls, case, candidates, top_k=5):
        similarities = cls._compute_embedding_similarities(case, candidates)
        if similarities is None:
            ranked = sorted(candidates, key=lambda lawyer: lawyer.experience_years, reverse=True)
            return [
                {
                    "lawyer": lawyer,
                    "score": min(max(lawyer.experience_years * 3, 1), 99),
                    "reasons": cls._build_default_reasons(case, lawyer),
                }
                for lawyer in ranked[:top_k]
            ]

        scored_candidates = []
        for idx, lawyer in enumerate(candidates):
            sim = similarities[idx]
            if sim is None:
                normalized_score = min(max(lawyer.experience_years * 3, 1), 99)
                sim = -1.0
            else:
                sim = float(sim)
                normalized_score = int(max(0, min(99, round(((sim + 1) / 2) * 99))))
            base_reasons = cls._build_default_reasons(case, lawyer)
            if sim >= 0.4:
                semantic = "Your case description closely matches this lawyer's practice profile."
            elif sim >= 0.25:
                semantic = "Good overlap between your case wording and this lawyer's expertise."
            else:
                semantic = None
            if semantic:
                merged = [semantic] + [r for r in base_reasons if r != semantic][:2]
            else:
                merged = base_reasons
            scored_candidates.append(
                {
                    "lawyer": lawyer,
                    "score": normalized_score,
                    "reasons": merged[:3],
                    "_similarity": sim,
                }
            )
        if getattr(settings, "MATCH_SCORE_V2_ENABLED", False):
            scored_candidates = cls._apply_hybrid_scores(case, scored_candidates, top_k=top_k)
        else:
            scored_candidates.sort(
                key=lambda item: (item["_similarity"], item["lawyer"].experience_years),
                reverse=True,
            )
            scored_candidates = scored_candidates[:top_k]
        for item in scored_candidates:
            item.pop("_similarity", None)
        return scored_candidates

    @classmethod
    def rank_with_gemini(cls, case, candidates, top_k=5):
        model = cls.get_gemini_model()
        if model is None or not candidates:
            return None

        candidate_map = {lawyer.id: lawyer for lawyer in candidates}
        prompt = (
            "You are a legal marketplace matching assistant.\n"
            "Rank the provided lawyers for the case below.\n"
            "Return JSON only with this schema:\n"
            '{"matches":[{"lawyer_id":123,"score":88,"reasons":["reason 1","reason 2","reason 3"]}]}\n'
            "Rules:\n"
            "- Only use lawyer IDs from the provided list.\n"
            "- Score must be an integer from 0 to 99.\n"
            "- Keep 2 or 3 concise reasons per lawyer.\n"
            "- Return at most the requested number of matches.\n\n"
            f"Requested top_k: {top_k}\n\n"
            f"Case details:\n{cls.build_case_prompt_block(case)}\n\n"
            f"Candidate lawyers:\n{cls.build_lawyer_summaries(candidates)}"
        )

        last_error = None
        for attempt in range(2):
            try:
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.2,
                        "response_mime_type": "application/json",
                    },
                )
                payload = json.loads(cls._strip_json_fence(response.text))
                raw_matches = payload.get("matches", []) if isinstance(payload, dict) else payload
                matches = []
                used_ids = set()

                for item in raw_matches:
                    if not isinstance(item, dict):
                        continue
                    raw_id = item.get("lawyer_id")
                    try:
                        lawyer_id = int(raw_id)
                    except (TypeError, ValueError):
                        continue
                    if lawyer_id not in candidate_map or lawyer_id in used_ids:
                        continue
                    raw_reasons = item.get("reasons")
                    if raw_reasons is None:
                        raw_reasons = []
                    if not isinstance(raw_reasons, (list, tuple)):
                        raw_reasons = []
                    reasons = [str(reason).strip() for reason in raw_reasons if str(reason).strip()]
                    matches.append(
                        {
                            "lawyer": candidate_map[lawyer_id],
                            "score": min(max(int(item.get("score", 0)), 0), 99),
                            "reasons": reasons[:3] or cls._build_default_reasons(case, candidate_map[lawyer_id]),
                        }
                    )
                    used_ids.add(lawyer_id)
                    if len(matches) >= top_k:
                        break

                if matches:
                    return matches
                last_error = ValueError("Gemini returned no valid matches")
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(1.5)

        logger.warning("Gemini ranking failed, falling back to embeddings: %s", last_error)
        return None

    @classmethod
    def enrich_match_reasons_with_gemini(cls, case, matches):
        """
        Replace display reasons with professional case↔lawyer fit copy. Does not change
        lawyer order, scores, or who was selected—only the text shown to the user.
        """
        model = cls.get_gemini_model()
        if model is None or not matches:
            return matches

        if getattr(settings, "GEMINI_ENRICH_REASONS", True) is False:
            return matches

        lawyer_ids = [m["lawyer"].id for m in matches]
        summaries_block = cls.build_lawyer_summaries([m["lawyer"] for m in matches])
        ids_list = ", ".join(str(i) for i in lawyer_ids)

        prompt = (
            "You help clients understand why each lawyer appears in their shortlist.\n"
            "Write 2 or 3 concise bullet points per lawyer explaining the practical fit "
            "between the CLIENT CASE and that lawyer's profile (practice areas, courts, city, experience).\n"
            "Tone: professional, neutral, trustworthy. Do not give legal advice or predict outcomes.\n"
            "Do not invent credentials; only use information implied by the case and lawyer blocks below.\n\n"
            f"CLIENT CASE:\n{cls.build_case_prompt_block(case)}\n\n"
            f"LAWYERS:\n{summaries_block}\n\n"
            "Return JSON only with this exact shape:\n"
            '{"summaries":[{"lawyer_id":<integer>,"reasons":["...","..."]}, ...]}\n'
            f"Include one entry for each of these lawyer IDs: {ids_list}\n"
        )

        last_error = None
        for attempt in range(2):
            try:
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.25,
                        "response_mime_type": "application/json",
                    },
                )
                payload = json.loads(cls._strip_json_fence(response.text))
                raw = payload.get("summaries", []) if isinstance(payload, dict) else payload
                by_id = {}
                if isinstance(raw, list):
                    for item in raw:
                        if not isinstance(item, dict):
                            continue
                        raw_id = item.get("lawyer_id")
                        try:
                            lid = int(raw_id)
                        except (TypeError, ValueError):
                            continue
                        rs = item.get("reasons")
                        if rs is None:
                            rs = []
                        if not isinstance(rs, (list, tuple)):
                            rs = []
                        cleaned = [str(x).strip() for x in rs if str(x).strip()]
                        if cleaned:
                            by_id[lid] = cleaned[:3]

                for m in matches:
                    lid = m["lawyer"].id
                    if lid in by_id:
                        m["reasons"] = by_id[lid]
                return matches
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(1.0)

        logger.warning("Gemini reason enrichment failed, keeping algorithmic reasons: %s", last_error)
        return matches

    @classmethod
    def get_best_matches(cls, case, top_k=5):
        candidates = cls.get_candidate_lawyers(case, getattr(settings, "MATCH_CANDIDATE_LIMIT", 30))
        if not candidates:
            return []

        gemini_matches = cls.rank_with_gemini(case, candidates, top_k=top_k)
        if gemini_matches is not None:
            matches = gemini_matches
        else:
            matches = cls._fallback_embedding_rank(case, candidates, top_k=top_k)

        # Keep Gemini as explanation/ranking helper, but score authority remains deterministic.
        if getattr(settings, "MATCH_SCORE_V2_ENABLED", False):
            match_by_id = {m["lawyer"].id: m for m in matches}
            rescored = cls._fallback_embedding_rank(case, [m["lawyer"] for m in matches], top_k=top_k)
            for row in rescored:
                existing = match_by_id.get(row["lawyer"].id)
                if existing:
                    existing["score"] = row["score"]

        return cls.enrich_match_reasons_with_gemini(case, matches)

    @classmethod
    def matches_to_cache_payload(cls, matches):
        """Serializable list for cache backends that struggle with pickled ORM instances."""
        return [
            {
                "lawyer_id": m["lawyer"].pk,
                "score": m["score"],
                "reasons": list(m.get("reasons") or []),
            }
            for m in matches
        ]

    @classmethod
    def matches_from_cache_payload(cls, case, payload):
        """Rebuild match dicts from cache payload; keeps lawyer rows fresh from the database."""
        from lawyers.models import LawyerProfile

        if not payload:
            return []
        ids = [row["lawyer_id"] for row in payload if isinstance(row, dict) and row.get("lawyer_id") is not None]
        if not ids:
            return []
        lawyers = {
            p.pk: p
            for p in LawyerProfile.objects.filter(pk__in=ids)
            .select_related("user", "city")
            .prefetch_related("practice_areas", "courts")
        }
        result = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            pk = row.get("lawyer_id")
            try:
                pk = int(pk)
            except (TypeError, ValueError):
                continue
            lawyer = lawyers.get(pk)
            if not lawyer:
                continue
            reasons = row.get("reasons")
            if not isinstance(reasons, list):
                reasons = []
            reasons = [str(r).strip() for r in reasons if str(r).strip()]
            result.append(
                {
                    "lawyer": lawyer,
                    "score": int(row.get("score", 0)),
                    "reasons": reasons[:3] or cls._build_default_reasons(case, lawyer),
                }
            )
        return result
