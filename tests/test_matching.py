import json
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from clients.models import Case
from lawyers.models import LawyerProfile
from lawyers.services.matching import MatchingService
from users.models import Category, City, Court, FeeBand, SubCategory, User


@override_settings(
    GEMINI_MODEL="gemini-test-model",
    MATCH_CANDIDATE_LIMIT=10,
)
class MatchingServiceTests(TestCase):
    def setUp(self):
        MatchingService._model = None
        MatchingService._gemini_model = None

        self.category = Category.objects.create(name="Family Law")
        self.subcategory = SubCategory.objects.create(category=self.category, name="Child Custody")
        self.city = City.objects.create(name="Lahore")
        self.other_city = City.objects.create(name="Karachi")
        self.court = Court.objects.create(name="High Court")
        self.fee_band = FeeBand.objects.create(name="Standard", min_fee=1000, max_fee=5000)

        self.client_user = User.objects.create_user(
            username="client1",
            email="client@example.com",
            password="pass12345",
            role="client",
        )
        self.case = Case.objects.create(
            client=self.client_user,
            title="Need help with child custody matter",
            description="Urgent family dispute involving custody and visitation.",
            category=self.category,
            subcategory=self.subcategory,
            city=self.city,
            court_level=self.court,
            fee_band=self.fee_band,
        )

        self.best_lawyer = self._create_lawyer(
            username="lawyer_best",
            email="best@example.com",
            city=self.city,
            experience_years=8,
            practice_areas=[self.subcategory],
            courts=[self.court],
        )
        self.other_lawyer = self._create_lawyer(
            username="lawyer_other",
            email="other@example.com",
            city=self.other_city,
            experience_years=3,
            practice_areas=[],
            courts=[],
        )

    def tearDown(self):
        MatchingService._model = None
        MatchingService._gemini_model = None

    def _create_lawyer(self, username, email, city, experience_years, practice_areas, courts):
        user = User.objects.create_user(
            username=username,
            email=email,
            password="pass12345",
            role="lawyer",
        )
        profile = LawyerProfile.objects.create(
            user=user,
            bar_enrollment=f"{username}-bar",
            city=city,
            experience_years=experience_years,
            verification_status="approved",
        )
        if practice_areas:
            profile.practice_areas.add(*practice_areas)
        if courts:
            profile.courts.add(*courts)
        return profile

    @override_settings(GEMINI_API_KEY="fake-key")
    def test_get_best_matches_uses_gemini_ranked_json(self):
        fake_model = Mock()
        rank_json = json.dumps(
            {
                "matches": [
                    {
                        "lawyer_id": self.best_lawyer.id,
                        "score": 91,
                        "reasons": ["Strong family law fit", "Practices in Lahore", "Handles High Court matters"],
                    }
                ]
            }
        )
        enrich_json = json.dumps(
            {
                "summaries": [
                    {
                        "lawyer_id": self.best_lawyer.id,
                        "reasons": [
                            "Professional fit summary A",
                            "Professional fit summary B",
                        ],
                    }
                ]
            }
        )
        fake_model.generate_content.side_effect = [
            Mock(text=rank_json),
            Mock(text=enrich_json),
        ]

        with patch.object(MatchingService, "get_gemini_model", return_value=fake_model):
            matches = MatchingService.get_best_matches(self.case, top_k=1)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["lawyer"], self.best_lawyer)
        self.assertEqual(matches[0]["score"], 91)
        self.assertEqual(matches[0]["reasons"], ["Professional fit summary A", "Professional fit summary B"])
        self.assertEqual(fake_model.generate_content.call_count, 2)

    @override_settings(GEMINI_API_KEY="fake-key")
    def test_gemini_string_lawyer_id_coerced(self):
        """LLMs often return lawyer_id as a string; we must still resolve candidates."""
        fake_model = Mock()
        rank_json = json.dumps(
            {
                "matches": [
                    {
                        "lawyer_id": str(self.best_lawyer.id),
                        "score": 90,
                        "reasons": ["String id should still match"],
                    }
                ]
            }
        )
        enrich_json = json.dumps(
            {
                "summaries": [
                    {"lawyer_id": self.best_lawyer.id, "reasons": ["Enriched after string id rank"]}
                ]
            }
        )
        fake_model.generate_content.side_effect = [Mock(text=rank_json), Mock(text=enrich_json)]

        with patch.object(MatchingService, "get_gemini_model", return_value=fake_model):
            matches = MatchingService.get_best_matches(self.case, top_k=1)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["lawyer"], self.best_lawyer)
        self.assertEqual(matches[0]["reasons"], ["Enriched after string id rank"])

    def test_cache_payload_round_trip(self):
        matches = [
            {
                "lawyer": self.best_lawyer,
                "score": 82,
                "reasons": ["Reason one", "Reason two"],
            }
        ]
        payload = MatchingService.matches_to_cache_payload(matches)
        restored = MatchingService.matches_from_cache_payload(self.case, payload)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["lawyer"].pk, self.best_lawyer.pk)
        self.assertEqual(restored[0]["score"], 82)
        self.assertEqual(restored[0]["reasons"], ["Reason one", "Reason two"])

    @override_settings(GEMINI_API_KEY="")
    def test_get_best_matches_falls_back_when_key_missing(self):
        fallback_result = [
            {
                "lawyer": self.best_lawyer,
                "score": 77,
                "reasons": ["Fallback semantic match"],
            }
        ]

        with patch.object(MatchingService, "_fallback_embedding_rank", return_value=fallback_result) as fallback_mock:
            matches = MatchingService.get_best_matches(self.case, top_k=1)

        fallback_mock.assert_called_once()
        self.assertEqual(matches, fallback_result)

    def test_candidate_retrieval_prioritizes_structured_matches(self):
        candidates = MatchingService.get_candidate_lawyers(self.case, limit=2)

        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0], self.best_lawyer)
