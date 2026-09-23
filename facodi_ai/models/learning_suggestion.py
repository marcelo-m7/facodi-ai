import hashlib
import json

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FacodiAILearningJob(models.Model):
    _name = "facodi.ai.learning.job"
    _description = "FACODI AI Learning Job"
    _order = "create_date desc, id desc"

    source_channel_id = fields.Many2one("slide.channel", ondelete="cascade", index=True)
    source_slide_id = fields.Many2one("slide.slide", ondelete="cascade", index=True)
    source_hash = fields.Char(required=True, readonly=True, index=True)
    state = fields.Selection(
        [("pending", "Pending"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")],
        default="pending", required=True, index=True,
    )
    retry_count = fields.Integer(default=0, readonly=True)
    error_message = fields.Text(readonly=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    analysis_id = fields.Many2one("facodi.ai.learning.analysis", readonly=True, ondelete="set null")

    _source_hash_unique = models.Constraint(
        "unique(source_channel_id, source_slide_id, source_hash)",
        "This source version already has an AI learning job.",
    )

    @api.constrains("source_channel_id", "source_slide_id")
    def _check_single_source(self):
        if any(bool(job.source_channel_id) == bool(job.source_slide_id) for job in self):
            raise ValidationError("An AI learning job requires exactly one course or content source.")

    @api.model
    def _source_values(self, source):
        values = {"id": source.id, "name": source.display_name}
        if source._name == "slide.channel":
            values["description"] = source.description or ""
        else:
            values["description"] = source.description or ""
        payload = json.dumps(values, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest(), payload

    @api.model
    def _enqueue_for_source(self, source):
        source.check_access("read")
        source_hash, _payload = self._source_values(source)
        source_field = "source_channel_id" if source._name == "slide.channel" else "source_slide_id"
        existing = self.search([(source_field, "=", source.id), ("source_hash", "=", source_hash), ("state", "in", ["pending", "running", "completed"])], limit=1)
        if existing:
            return existing
        return self.create({source_field: source.id, "source_hash": source_hash})

    @api.model
    def _cron_process_pending(self, limit=20):
        jobs = self.search([("state", "=", "pending")], limit=limit)
        for job in jobs:
            job._process()

    def _process(self):
        self.ensure_one()
        if self.state != "pending":
            return False
        now = fields.Datetime.now()
        self.write({"state": "running", "started_at": now, "error_message": False})
        try:
            source = self.source_channel_id or self.source_slide_id
            _source_hash, payload = self._source_values(source)
            analysis = self.env["facodi.ai.learning.analysis"].create({
                "job_id": self.id, "source_channel_id": self.source_channel_id.id,
                "source_slide_id": self.source_slide_id.id, "source_hash": self.source_hash,
                "structured_result": {"source": json.loads(payload), "status": "awaiting_provider_analysis"},
            })
            self.write({"state": "completed", "analysis_id": analysis.id, "finished_at": fields.Datetime.now()})
        except Exception as error:
            self.write({"state": "failed", "retry_count": self.retry_count + 1, "error_message": str(error), "finished_at": fields.Datetime.now()})
            raise
        return True


class FacodiAILearningAnalysis(models.Model):
    _name = "facodi.ai.learning.analysis"
    _description = "FACODI AI Learning Analysis"
    _order = "create_date desc, id desc"

    job_id = fields.Many2one("facodi.ai.learning.job", required=True, ondelete="cascade", index=True)
    source_channel_id = fields.Many2one("slide.channel", ondelete="cascade", index=True)
    source_slide_id = fields.Many2one("slide.slide", ondelete="cascade", index=True)
    source_hash = fields.Char(required=True, index=True)
    provider_code = fields.Char(readonly=True)
    model_name = fields.Char(readonly=True)
    prompt_version = fields.Char(readonly=True)
    structured_result = fields.Json(readonly=True)


class FacodiAILearningSuggestion(models.Model):
    _name = "facodi.ai.learning.suggestion"
    _description = "FACODI AI Learning Suggestion"
    _order = "confidence desc, id desc"

    source_channel_id = fields.Many2one("slide.channel", ondelete="cascade", index=True)
    source_slide_id = fields.Many2one("slide.slide", ondelete="cascade", index=True)
    target_unit_id = fields.Many2one("facodi.learning.curriculum.unit", ondelete="restrict", index=True)
    target_channel_id = fields.Many2one("slide.channel", ondelete="restrict", index=True)
    target_slide_id = fields.Many2one("slide.slide", ondelete="restrict", index=True)
    relation_type = fields.Selection([
        ("covers", "Covers"), ("partial", "Partial"), ("supports", "Supports"), ("equivalent", "Equivalent"),
        ("related", "Related"), ("alternative", "Alternative"), ("continuation", "Continuation"),
        ("complements", "Complements"), ("prerequisite", "Prerequisite"), ("recommended", "Recommended"),
    ], required=True, default="related", index=True)
    confidence = fields.Float(required=True, digits=(5, 4))
    rationale = fields.Text(required=True)
    analysis_id = fields.Many2one("facodi.ai.learning.analysis", ondelete="set null", index=True)
    provider_code = fields.Char(readonly=True)
    model_name = fields.Char(readonly=True)
    prompt_version = fields.Char(readonly=True)
    state = fields.Selection([( "pending_review", "Pending Review"), ("approved", "Approved"), ("rejected", "Rejected")], default="pending_review", required=True, index=True)
    reviewer_id = fields.Many2one("res.users", readonly=True)
    decided_at = fields.Datetime(readonly=True)
    review_note = fields.Text()
    official_model = fields.Char(readonly=True)
    official_res_id = fields.Integer(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "pending_review") != "pending_review" or any(
                vals.get(field_name)
                for field_name in ("reviewer_id", "decided_at", "official_model", "official_res_id")
            ):
                raise AccessError("Use the explicit AI suggestion review actions.")
        return super().create(vals_list)

    def write(self, vals):
        protected = {"state", "reviewer_id", "decided_at", "official_model", "official_res_id"}
        if protected & vals.keys():
            raise AccessError("Use the explicit AI suggestion review actions.")
        if any(suggestion.state != "pending_review" for suggestion in self):
            raise AccessError("Reviewed AI suggestions are immutable audit history.")
        return super().write(vals)

    @api.constrains("source_channel_id", "source_slide_id", "target_unit_id", "target_channel_id", "target_slide_id", "confidence")
    def _check_shape(self):
        for suggestion in self:
            if bool(suggestion.source_channel_id) == bool(suggestion.source_slide_id):
                raise ValidationError("A suggestion requires exactly one source.")
            if sum(bool(value) for value in (suggestion.target_unit_id, suggestion.target_channel_id, suggestion.target_slide_id)) != 1:
                raise ValidationError("A suggestion requires exactly one target.")
            if not 0 <= suggestion.confidence <= 1:
                raise ValidationError("Confidence must be between zero and one.")

    def _check_reviewer(self):
        if self.env.uid != SUPERUSER_ID and not self.env.user.has_group("website_slides.group_website_slides_manager"):
            raise AccessError("Only eLearning Managers can review AI suggestions.")

    def _materialize(self):
        self.ensure_one()
        if self.source_channel_id and self.target_unit_id:
            model = self.env["facodi.learning.curriculum.coverage"]
            domain = [("channel_id", "=", self.source_channel_id.id), ("curriculum_unit_id", "=", self.target_unit_id.id), ("coverage_type", "=", self.relation_type)]
            existing = model.search(domain, limit=1)
            record = existing or model._create_generated({"channel_id": self.source_channel_id.id, "curriculum_unit_id": self.target_unit_id.id, "coverage_type": self.relation_type, "confidence": self.confidence, "evidence": {"ai_suggestion_id": self.id, "rationale": self.rationale}, "evaluation_version": self.prompt_version})
        elif self.source_channel_id and self.target_channel_id:
            model = self.env["facodi.learning.course.mapping"]
            domain = [("source_channel_id", "=", self.source_channel_id.id), ("target_channel_id", "=", self.target_channel_id.id), ("mapping_type", "=", self.relation_type)]
            existing = model.search(domain, limit=1)
            record = existing or model._create_generated({"source_channel_id": self.source_channel_id.id, "target_channel_id": self.target_channel_id.id, "mapping_type": self.relation_type, "confidence": self.confidence, "evidence": {"ai_suggestion_id": self.id, "rationale": self.rationale}, "ranking_version": self.prompt_version})
        elif self.source_slide_id and self.target_slide_id:
            model = self.env["facodi.learning.mapping"]
            domain = [("source_slide_id", "=", self.source_slide_id.id), ("target_slide_id", "=", self.target_slide_id.id), ("mapping_type", "=", self.relation_type)]
            existing = model.search(domain, limit=1)
            record = existing or model.with_context(default_origin="analysis").create({"source_slide_id": self.source_slide_id.id, "target_slide_id": self.target_slide_id.id, "mapping_type": self.relation_type, "confidence": self.confidence})
        else:
            raise ValidationError("This source and target combination is not supported.")
        return record

    def action_approve(self):
        self._check_reviewer()
        for suggestion in self:
            if suggestion.state != "pending_review":
                raise ValidationError("Only pending suggestions can be reviewed.")
            record = suggestion._materialize()
            super(FacodiAILearningSuggestion, suggestion).write({"state": "approved", "reviewer_id": self.env.uid, "decided_at": fields.Datetime.now(), "official_model": record._name, "official_res_id": record.id})
        return True

    def action_reject(self):
        self._check_reviewer()
        if any(suggestion.state != "pending_review" for suggestion in self):
            raise ValidationError("Only pending suggestions can be reviewed.")
        super(FacodiAILearningSuggestion, self).write({"state": "rejected", "reviewer_id": self.env.uid, "decided_at": fields.Datetime.now()})
        return True
