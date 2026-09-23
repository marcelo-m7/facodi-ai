from odoo.tests import TransactionCase

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

    def test_course_job_is_idempotent(self):
        Job = self.env["facodi.ai.learning.job"]
        first = Job._enqueue_for_source(self.course)
        second = Job._enqueue_for_source(self.course)
        self.assertEqual(first, second)
        self.assertEqual(first.state, "pending")

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
