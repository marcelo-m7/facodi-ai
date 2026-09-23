import hashlib
import json

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from ..services.contracts import LearningAnalysisResult


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
    max_retries = fields.Integer(default=3, required=True, readonly=True)
    next_retry_at = fields.Datetime(readonly=True, index=True)
    error_message = fields.Text(readonly=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    analysis_id = fields.Many2one("facodi.ai.learning.analysis", readonly=True, ondelete="set null")
    profile_id = fields.Many2one("facodi.ai.profile", readonly=True, ondelete="restrict")

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
        profile = self._learning_profile()
        return self.create(
            {source_field: source.id, "source_hash": source_hash, "profile_id": profile.id}
        )

    @api.model
    def _learning_profile(self):
        profile_id = self.env["ir.config_parameter"].sudo().get_param(
            "facodi_ai.learning_profile_id"
        )
        profile = self.env["facodi.ai.profile"].browse(int(profile_id or 0)).exists()
        if not profile or not profile.active:
            raise ValidationError(
                "Configure an active FACODI AI learning profile before requesting analysis."
            )
        if profile.capability not in {"classification", "extraction", "generation"}:
            raise ValidationError("The FACODI AI learning profile must support structured analysis.")
        return profile

    @api.model
    def _cron_process_pending(self, limit=20):
        now = fields.Datetime.now()
        jobs = self.search(
            [
                ("state", "=", "pending"),
                "|",
                ("next_retry_at", "=", False),
                ("next_retry_at", "<=", now),
            ],
            limit=limit,
        )
        for job in jobs:
            job._process()

    def _source_payload(self):
        self.ensure_one()
        source = self.source_channel_id or self.source_slide_id
        _source_hash, payload = self._source_values(source)
        return json.loads(payload)

    def _provider_instructions(self):
        self.ensure_one()
        custom = self.profile_id.prompt_id.custom_instructions or ""
        instructions = (
            "Analyse the FACODI eLearning source. Return only evidence-grounded "
            "mapping candidates. Do not claim academic equivalence, credits, "
            "enrolment, or completeness. Each candidate must use an existing target ID."
        )
        return f"{instructions}\n\nAdministrator instructions:\n{custom.strip()}" if custom else instructions

    def _provider_prompt(self, source_payload):
        return json.dumps(
            {
                "source": source_payload,
                "allowed_targets": ["unit", "channel", "slide"],
                "instruction": "Return zero or more reviewable mapping candidates.",
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def _create_suggestions(self, analysis, result):
        self.ensure_one()
        suggestion_model = self.env["facodi.ai.learning.suggestion"]
        source_values = (
            {"source_channel_id": self.source_channel_id.id}
            if self.source_channel_id
            else {"source_slide_id": self.source_slide_id.id}
        )
        target_models = {
            "unit": "facodi.learning.curriculum.unit",
            "channel": "slide.channel",
            "slide": "slide.slide",
        }
        for candidate in result.candidates:
            if self.source_channel_id:
                if candidate.target_kind == "unit":
                    allowed_relations = {"covers", "partial", "supports", "equivalent"}
                elif candidate.target_kind == "channel":
                    allowed_relations = {
                        "related",
                        "alternative",
                        "continuation",
                        "complements",
                        "equivalent",
                        "prerequisite",
                    }
                else:
                    continue
            elif candidate.target_kind == "slide":
                allowed_relations = {"related", "prerequisite", "recommended", "supports"}
            else:
                continue
            if candidate.relation_type not in allowed_relations:
                continue
            target_field = f"target_{candidate.target_kind}_id"
            target = self.env[target_models[candidate.target_kind]].browse(
                candidate.target_id
            ).exists()
            if not target:
                continue
            if (
                candidate.target_kind == "channel"
                and target == self.source_channel_id
            ) or (
                candidate.target_kind == "slide" and target == self.source_slide_id
            ):
                continue
            domain = [
                *( (field, "=", value) for field, value in source_values.items() ),
                (target_field, "=", target.id),
                ("relation_type", "=", candidate.relation_type),
                ("analysis_id", "=", analysis.id),
            ]
            if suggestion_model.search(domain, limit=1):
                continue
            suggestion_model.create(
                {
                    **source_values,
                    target_field: target.id,
                    "relation_type": candidate.relation_type,
                    "confidence": candidate.confidence,
                    "rationale": candidate.rationale,
                    "analysis_id": analysis.id,
                    "provider_code": analysis.provider_code,
                    "model_name": analysis.model_name,
                    "prompt_version": analysis.prompt_version,
                }
            )

    def _process(self):
        self.ensure_one()
        if self.state != "pending":
            return False
        now = fields.Datetime.now()
        self.write(
            {
                "state": "running",
                "started_at": now,
                "error_message": False,
                "next_retry_at": False,
            }
        )
        try:
            if not self.profile_id:
                self.write({"profile_id": self._learning_profile().id})
            source_payload = self._source_payload()
            resolved = self.env["facodi.ai.profile.resolver"]._resolve(self.profile_id)
            result = self.env["facodi.ai.service"]._run(
                profile=self.profile_id,
                input_payload={"source": source_payload},
                output_type=LearningAnalysisResult,
                instructions=self._provider_instructions(),
                user_prompt=self._provider_prompt(source_payload),
            )
            analysis = self.env["facodi.ai.learning.analysis"].create(
                {
                    "job_id": self.id,
                    "source_channel_id": self.source_channel_id.id,
                    "source_slide_id": self.source_slide_id.id,
                    "source_hash": self.source_hash,
                    "provider_code": resolved.provider_code,
                    "model_name": resolved.model_name,
                    "prompt_version": str(self.profile_id.prompt_id.version or ""),
                    "structured_result": result.model_dump(mode="json"),
                }
            )
            self._create_suggestions(analysis, result)
            self.write(
                {
                    "state": "completed",
                    "analysis_id": analysis.id,
                    "finished_at": fields.Datetime.now(),
                }
            )
        except Exception as error:
            retries = self.retry_count + 1
            delay_seconds = min(2 ** (retries - 1), 60)
            self.write(
                {
                    "state": "failed" if retries >= self.max_retries else "pending",
                    "retry_count": retries,
                    "next_retry_at": fields.Datetime.add(now, seconds=delay_seconds)
                    if retries < self.max_retries
                    else False,
                    "error_message": str(error),
                    "finished_at": fields.Datetime.now(),
                }
            )
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
            record = existing or model.create(
                {
                    "source_slide_id": self.source_slide_id.id,
                    "target_slide_id": self.target_slide_id.id,
                    "mapping_type": self.relation_type,
                    "confidence": self.confidence,
                    "origin": "analysis",
                    "analysis_provenance_model": "facodi.ai.learning.analysis",
                    "analysis_provenance_res_id": self.analysis_id.id,
                }
            )
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
