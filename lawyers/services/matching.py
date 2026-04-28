import json
import logging
import re
import time

from django.conf import settings
from django.db.models import Q

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
        practice_areas = " ".join(pa.name for pa in lawyer.practice_areas.all())
        courts = " ".join(c.name for c in lawyer.courts.all())
        city = lawyer.city.name if lawyer.city else ""
        display_name = lawyer.user.get_full_name() or lawyer.user.username
        return cls.preprocess_text(
            f"{display_name} {practice_areas} {courts} {city} Experience: {lawyer.experience_years} years."
        )

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
            import numpy as np
            from sklearn.metrics.pairwise import cosine_similarity
        except (ImportError, RuntimeError) as exc:
            logger.warning("Embedding dependencies unavailable: %s", exc)
            return None

        model = cls.get_model()
        if model is None or not candidates:
            return None

        case_embedding = model.encode([cls.build_case_prompt_block(case)])[0]
        lawyer_texts = [cls.get_lawyer_embedding_text(lawyer) for lawyer in candidates]
        if not lawyer_texts:
            lawyer_embeddings = np.zeros((len(candidates), 384))
        else:
            lawyer_embeddings = model.encode(lawyer_texts)
        return cosine_similarity([case_embedding], lawyer_embeddings)[0]

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
            normalized_score = int(max(0, min(99, round(((float(similarities[idx]) + 1) / 2) * 99))))
            sim = float(similarities[idx])
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

        scored_candidates.sort(
            key=lambda item: (item["_similarity"], item["lawyer"].experience_years),
            reverse=True,
        )
        for item in scored_candidates:
            item.pop("_similarity", None)
        return scored_candidates[:top_k]

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
