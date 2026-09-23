from unittest.mock import patch

from odoo.tests import TransactionCase

from odoo.addons.facodi_ai.models.ai_service import FacodiAIService
from odoo.addons.facodi_ai.services.contracts import LearningAnalysisResult
from odoo.addons.facodi_ai.services.profile_resolver import (
    FacodiAIProfileResolver,
    ResolvedAIProfile,
)

class TestLearningBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reference = cls.env["facodi.learning.curriculum.reference"].create({
            "institution": "Test Institution",
            "programme_name": "Test Programme",
            "academic_year": "2026/27",
            "provider": "test",
            "external_id": "ai-learning-bridge",
            "website_published": True,
            "validated_at": "2026-01-01 00:00:00",
        })
        cls.unit = cls.env["facodi.learning.curriculum.unit"].create({
            "reference_id": cls.reference.id,
            "external_unit_code": "AI-101",
            "name": "AI Bridge Unit",
            "curricular_year": 1,
            "classification": "mandatory",
        })
        cls.course = cls.env["slide.channel"].create({"name": "AI Bridge Course"})
        cls.source_slide = cls.env["slide.slide"].create(
            {
                "name": "AI Bridge Source",
                "channel_id": cls.course.id,
                "slide_category": "article",
            }
        )
        cls.target_slide = cls.env["slide.slide"].create(
            {
                "name": "AI Bridge Target",
                "channel_id": cls.course.id,
                "slide_category": "article",
            }
        )
        cls.profile = cls.env["facodi.ai.profile"].create(
            {
                "name": "Learning analysis",
                "code": "learning_analysis",
                "capability": "classification",
                "model_override": "test-model",
            }
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "facodi_ai.learning_profile_id", cls.profile.id
        )

    def _resolved_profile(self):
        return ResolvedAIProfile(
            profile_id=self.profile.id,
            provider_code="openai",
            connection_id=None,
            model_name="test-model",
            timeout=60,
            max_tokens=1024,
            retries=0,
            structured_output=True,
            temperature=None,
        )

    def test_course_job_is_idempotent(self):
        Job = self.env["facodi.ai.learning.job"]
        first = Job._enqueue_for_source(self.course)
        second = Job._enqueue_for_source(self.course)
        self.assertEqual(first, second)
        self.assertEqual(first.state, "pending")

    def test_provider_job_creates_auditable_reviewable_suggestion(self):
        job = self.env["facodi.ai.learning.job"]._enqueue_for_source(self.course)
        output = LearningAnalysisResult.model_validate(
            {
                "candidates": [
                    {
                        "target_kind": "unit",
                        "target_id": self.unit.id,
                        "relation_type": "covers",
                        "confidence": 0.9,
                        "rationale": "The course objectives match the reviewed unit scope.",
                    }
                ]
            }
        )

        with (
            patch.object(
                FacodiAIProfileResolver,
                "_resolve",
                return_value=self._resolved_profile(),
            ),
            patch.object(FacodiAIService, "_run", return_value=output),
        ):
            job._process()

        self.assertEqual(job.state, "completed")
        self.assertEqual(job.analysis_id.provider_code, "openai")
        self.assertEqual(job.analysis_id.model_name, "test-model")
        suggestion = self.env["facodi.ai.learning.suggestion"].search(
            [("analysis_id", "=", job.analysis_id.id)]
        )
        self.assertEqual(len(suggestion), 1)
        self.assertEqual(suggestion.state, "pending_review")
        self.assertEqual(suggestion.target_unit_id, self.unit)

    def test_provider_failure_is_retried_without_duplicate_jobs(self):
        job = self.env["facodi.ai.learning.job"]._enqueue_for_source(self.course)

        with (
            patch.object(
                FacodiAIProfileResolver,
                "_resolve",
                return_value=self._resolved_profile(),
            ),
            patch.object(FacodiAIService, "_run", side_effect=RuntimeError("provider unavailable")),
        ):
            job._process()

        self.assertEqual(job.state, "pending")
        self.assertEqual(job.retry_count, 1)
        self.assertTrue(job.next_retry_at)
        self.assertIn("provider unavailable", job.error_message)
        self.assertEqual(
            self.env["facodi.ai.learning.job"]._enqueue_for_source(self.course), job
        )

    def test_approved_slide_suggestion_preserves_ai_analysis_provenance(self):
        job = self.env["facodi.ai.learning.job"]._enqueue_for_source(self.source_slide)
        output = LearningAnalysisResult.model_validate(
            {
                "candidates": [
                    {
                        "target_kind": "slide",
                        "target_id": self.target_slide.id,
                        "relation_type": "related",
                        "confidence": 0.8,
                        "rationale": "The two learning resources cover adjacent concepts.",
                    }
                ]
            }
        )

        with (
            patch.object(
                FacodiAIProfileResolver,
                "_resolve",
                return_value=self._resolved_profile(),
            ),
            patch.object(FacodiAIService, "_run", return_value=output),
        ):
            job._process()

        suggestion = self.env["facodi.ai.learning.suggestion"].search(
            [("analysis_id", "=", job.analysis_id.id)]
        )
        suggestion.action_approve()
        mapping = self.env[suggestion.official_model].browse(suggestion.official_res_id)
        self.assertEqual(mapping.origin, "analysis")
        self.assertEqual(mapping.analysis_provenance_model, "facodi.ai.learning.analysis")
        self.assertEqual(mapping.analysis_provenance_res_id, job.analysis_id.id)

    def test_approved_coverage_suggestion_creates_one_proposal(self):
        suggestion = self.env["facodi.ai.learning.suggestion"].create({
            "source_channel_id": self.course.id,
            "target_unit_id": self.unit.id,
            "relation_type": "covers",
            "confidence": 0.9,
            "rationale": "Reviewed evidence links the course and curricular unit.",
        })
        suggestion.action_approve()
        self.assertEqual(suggestion.state, "approved")
        self.assertEqual(suggestion.official_model, "facodi.learning.curriculum.coverage")
        coverage = self.env[suggestion.official_model].browse(suggestion.official_res_id)
        self.assertEqual(coverage.state, "proposed")
        self.assertEqual(coverage.origin, "analysis")

    def test_rejected_suggestion_creates_no_mapping(self):
        suggestion = self.env["facodi.ai.learning.suggestion"].create({
            "source_channel_id": self.course.id,
            "target_unit_id": self.unit.id,
            "relation_type": "partial",
            "confidence": 0.5,
            "rationale": "Insufficient evidence for complete coverage.",
        })
        suggestion.action_reject()
        self.assertEqual(suggestion.state, "rejected")
        self.assertFalse(suggestion.official_res_id)
