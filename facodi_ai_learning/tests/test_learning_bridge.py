from unittest.mock import patch

from psycopg2 import IntegrityError
from odoo.exceptions import ValidationError
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

    def test_database_uniqueness_covers_course_and_content_sources(self):
        Job = self.env["facodi.ai.learning.job"]
        for source, field_name in (
            (self.course, "source_channel_id"),
            (self.source_slide, "source_slide_id"),
        ):
            first = Job._enqueue_for_source(source)
            with self.assertRaises(IntegrityError), self.env.cr.savepoint():
                Job.create(
                    {
                        field_name: source.id,
                        "source_hash": first.source_hash,
                        "profile_id": self.profile.id,
                    }
                )

    def test_terminal_failed_job_is_reactivated_without_duplicate(self):
        Job = self.env["facodi.ai.learning.job"]
        job = Job._enqueue_for_source(self.course)
        job.write({"max_retries": 1})

        with (
            patch.object(
                FacodiAIProfileResolver,
                "_resolve",
                return_value=self._resolved_profile(),
            ),
            patch.object(
                FacodiAIService,
                "_run",
                side_effect=RuntimeError("provider unavailable"),
            ),
        ):
            job._process()

        self.assertEqual(job.state, "failed")
        self.assertEqual(job.retry_count, 1)
        self.assertTrue(job.error_message)

        retried = Job._enqueue_for_source(self.course)

        self.assertEqual(retried, job)
        self.assertEqual(retried.state, "pending")
        self.assertEqual(retried.retry_count, 0)
        self.assertFalse(retried.next_retry_at)
        self.assertFalse(retried.error_message)
        self.assertFalse(retried.started_at)
        self.assertFalse(retried.finished_at)
        self.assertEqual(retried.profile_id, self.profile)
        self.assertEqual(
            Job.search_count(
                [
                    ("source_channel_id", "=", self.course.id),
                    ("source_hash", "=", job.source_hash),
                ]
            ),
            1,
        )

    def test_missing_learning_profile_blocks_explicit_request_without_job(self):
        params = self.env["ir.config_parameter"].sudo()
        previous = params.get_param("facodi_ai.learning_profile_id")
        before = self.env["facodi.ai.learning.job"].search_count([])
        params.set_param("facodi_ai.learning_profile_id", "")
        try:
            with self.assertRaisesRegex(
                ValidationError,
                "Configure an active FACODI AI learning profile",
            ):
                self.env["facodi.ai.learning.job"]._enqueue_for_source(self.course)
        finally:
            params.set_param("facodi_ai.learning_profile_id", previous or self.profile.id)

        self.assertEqual(
            self.env["facodi.ai.learning.job"].search_count([]),
            before,
        )

    def test_disabled_ai_preserves_manual_flow_without_learning_side_effects(self):
        job = self.env["facodi.ai.learning.job"]._enqueue_for_source(self.course)
        params = self.env["ir.config_parameter"].sudo()
        previous = params.get_param("facodi_ai.enabled")
        before = {
            "analysis": self.env["facodi.ai.learning.analysis"].search_count([]),
            "suggestion": self.env["facodi.ai.learning.suggestion"].search_count([]),
            "coverage": self.env[
                "facodi.learning.curriculum.coverage"
            ].search_count([]),
            "course_mapping": self.env[
                "facodi.learning.course.mapping"
            ].search_count([]),
            "content_mapping": self.env[
                "facodi.learning.mapping"
            ].search_count([]),
        }
        params.set_param("facodi_ai.enabled", "0")
        try:
            with patch.object(
                FacodiAIProfileResolver,
                "_resolve",
                return_value=self._resolved_profile(),
            ) as resolver:
                job._process()
                self.assertEqual(resolver.call_count, 1)
        finally:
            if previous is None:
                params.set_param("facodi_ai.enabled", "1")
            else:
                params.set_param("facodi_ai.enabled", previous)

        job.invalidate_recordset()
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.retry_count, 1)
        self.assertFalse(job.analysis_id)
        self.assertEqual(
            self.env["facodi.ai.learning.analysis"].search_count([]),
            before["analysis"],
        )
        self.assertEqual(
            self.env["facodi.ai.learning.suggestion"].search_count([]),
            before["suggestion"],
        )
        self.assertEqual(
            self.env["facodi.learning.curriculum.coverage"].search_count([]),
            before["coverage"],
        )
        self.assertEqual(
            self.env["facodi.learning.course.mapping"].search_count([]),
            before["course_mapping"],
        )
        self.assertEqual(
            self.env["facodi.learning.mapping"].search_count([]),
            before["content_mapping"],
        )

    def test_cron_never_enqueues_unrequested_learning_sources(self):
        unrequested = self.env["slide.channel"].create(
            {"name": "Unrequested AI Learning Course"}
        )
        Job = self.env["facodi.ai.learning.job"]
        before = Job.search_count([])

        Job._cron_process_pending()

        self.assertEqual(Job.search_count([]), before)
        self.assertFalse(
            Job.search(
                [("source_channel_id", "=", unrequested.id)],
                limit=1,
            )
        )

    def test_course_prompt_contains_only_explicit_existing_target_ids(self):
        job = self.env["facodi.ai.learning.job"]._enqueue_for_source(self.course)
        prompt = job._provider_prompt(job._source_payload())
        payload = __import__("json").loads(prompt)

        unit_ids = {
            row["id"] for row in payload["candidate_targets"]["unit"]
        }
        self.assertIn(self.unit.id, unit_ids)
        self.assertIn("unit", payload["allowed_targets"])
        self.assertEqual(payload["candidate_targets"]["slide"], [])

    def test_provider_candidate_outside_grounded_catalogue_is_ignored(self):
        private_reference = self.env["facodi.learning.curriculum.reference"].create({
            "institution": "Hidden Institution",
            "programme_name": "Hidden Programme",
            "academic_year": "2026/27",
            "provider": "test",
            "external_id": "ai-learning-hidden-reference",
            "website_published": False,
        })
        hidden_unit = self.env["facodi.learning.curriculum.unit"].create({
            "reference_id": private_reference.id,
            "external_unit_code": "HIDDEN-101",
            "name": "Hidden Unit",
            "curricular_year": 1,
            "classification": "mandatory",
        })
        job = self.env["facodi.ai.learning.job"]._enqueue_for_source(self.course)
        output = LearningAnalysisResult.model_validate(
            {
                "candidates": [
                    {
                        "target_kind": "unit",
                        "target_id": hidden_unit.id,
                        "relation_type": "supports",
                        "confidence": 0.9,
                        "rationale": "Provider returned an existing but non-candidate target.",
                    }
                ]
            }
        )

        analysis = self.env["facodi.ai.learning.analysis"].create(
            {
                "job_id": job.id,
                "source_channel_id": self.course.id,
                "source_hash": job.source_hash,
                "provider_code": "openai",
                "model_name": "test-model",
                "prompt_version": "1",
                "structured_result": output.model_dump(mode="json"),
            }
        )
        job._create_suggestions(analysis, output)
        self.assertFalse(
            self.env["facodi.ai.learning.suggestion"].search(
                [("analysis_id", "=", analysis.id)]
            )
        )

    def test_provider_job_creates_auditable_reviewable_suggestion(self):
        job = self.env["facodi.ai.learning.job"]._enqueue_for_source(self.course)
        coverage_domain = [
            ("channel_id", "=", self.course.id),
            ("curriculum_unit_id", "=", self.unit.id),
        ]
        coverage_before = self.env[
            "facodi.learning.curriculum.coverage"
        ].search_count(coverage_domain)
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
        self.assertFalse(suggestion.official_res_id)
        self.assertEqual(
            self.env["facodi.learning.curriculum.coverage"].search_count(
                coverage_domain
            ),
            coverage_before,
        )

    def test_bridge_persistence_failure_rolls_back_partial_analysis(self):
        Job = self.env["facodi.ai.learning.job"]
        Analysis = self.env["facodi.ai.learning.analysis"]
        Suggestion = self.env["facodi.ai.learning.suggestion"]
        job = Job._enqueue_for_source(self.course)
        output = LearningAnalysisResult.model_validate(
            {
                "candidates": [
                    {
                        "target_kind": "unit",
                        "target_id": self.unit.id,
                        "relation_type": "supports",
                        "confidence": 0.8,
                        "rationale": "Valid candidate before simulated bridge failure.",
                    }
                ]
            }
        )
        analysis_before = Analysis.search_count([])
        suggestion_before = Suggestion.search_count([])

        def fail_after_partial_suggestion(job_record, analysis, result):
            Suggestion.create(
                {
                    "source_channel_id": job_record.source_channel_id.id,
                    "target_unit_id": self.unit.id,
                    "relation_type": "supports",
                    "confidence": 0.8,
                    "rationale": "Partial suggestion that must roll back.",
                    "analysis_id": analysis.id,
                    "provider_code": analysis.provider_code,
                    "model_name": analysis.model_name,
                    "prompt_version": analysis.prompt_version,
                }
            )
            raise RuntimeError("bridge persistence failed")

        with (
            patch.object(
                FacodiAIProfileResolver,
                "_resolve",
                return_value=self._resolved_profile(),
            ),
            patch.object(FacodiAIService, "_run", return_value=output),
            patch.object(
                type(job),
                "_create_suggestions",
                fail_after_partial_suggestion,
            ),
        ):
            job._process()

        job.invalidate_recordset()
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.retry_count, 1)
        self.assertFalse(job.analysis_id)
        self.assertEqual(Analysis.search_count([]), analysis_before)
        self.assertEqual(Suggestion.search_count([]), suggestion_before)
        self.assertIn("bridge persistence failed", job.error_message)

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

    def test_provider_failure_never_persists_secret_or_traceback(self):
        job = self.env["facodi.ai.learning.job"]._enqueue_for_source(self.course)

        with (
            patch.object(
                FacodiAIProfileResolver,
                "_resolve",
                return_value=self._resolved_profile(),
            ),
            patch.object(
                FacodiAIService,
                "_run",
                side_effect=RuntimeError(
                    "Authorization: sk-secret-value\n"
                    "Traceback (most recent call last): hidden"
                ),
            ),
        ):
            job._process()

        self.assertEqual(job.state, "pending")
        self.assertEqual(job.retry_count, 1)
        self.assertNotIn("sk-secret-value", job.error_message)
        self.assertNotIn("Traceback", job.error_message)
        self.assertIn("Authorization=[redacted]", job.error_message)

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
