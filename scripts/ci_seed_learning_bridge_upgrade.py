"""Seed legacy facodi_ai learning rows before the bridge-split upgrade."""

channel = env["slide.channel"].create(
    {"name": "FACODI AI bridge upgrade sentinel source"}
)
target_channel = env["slide.channel"].create(
    {"name": "FACODI AI bridge upgrade sentinel target"}
)
profile = env["facodi.ai.profile"].create(
    {
        "name": "FACODI AI bridge upgrade sentinel profile",
        "code": "ci_learning_bridge_upgrade",
        "capability": "classification",
        "model_override": "test-model",
    }
)
job = env["facodi.ai.learning.job"].create(
    {
        "source_channel_id": channel.id,
        "source_hash": "facodi-ai-learning-bridge-upgrade-sentinel",
        "profile_id": profile.id,
    }
)
analysis = env["facodi.ai.learning.analysis"].create(
    {
        "job_id": job.id,
        "source_channel_id": channel.id,
        "source_hash": job.source_hash,
        "provider_code": "openai",
        "model_name": "legacy-test-model",
        "prompt_version": "legacy-v1",
        "structured_result": {"candidates": []},
    }
)
suggestion = env["facodi.ai.learning.suggestion"].create(
    {
        "source_channel_id": channel.id,
        "target_channel_id": target_channel.id,
        "relation_type": "related",
        "confidence": 0.75,
        "rationale": "FACODI AI bridge upgrade sentinel suggestion",
        "analysis_id": analysis.id,
        "provider_code": "openai",
        "model_name": "legacy-test-model",
        "prompt_version": "legacy-v1",
    }
)

params = env["ir.config_parameter"].sudo()
for key, value in {
    "facodi_ai.ci_bridge_job_id": job.id,
    "facodi_ai.ci_bridge_analysis_id": analysis.id,
    "facodi_ai.ci_bridge_suggestion_id": suggestion.id,
}.items():
    params.set_param(key, value)

legacy_xmlids = [
    "ir_cron_facodi_ai_learning_jobs",
    "view_facodi_ai_learning_suggestion_list",
    "view_facodi_ai_learning_suggestion_form",
    "action_facodi_ai_learning_suggestions",
    "menu_facodi_ai_learning_suggestions",
    "access_facodi_ai_learning_job_manager",
    "access_facodi_ai_learning_analysis_manager",
    "access_facodi_ai_learning_suggestion_manager",
    "model_facodi_ai_learning_job",
    "model_facodi_ai_learning_analysis",
    "model_facodi_ai_learning_suggestion",
]
for name in legacy_xmlids:
    record = env.ref(f"facodi_ai.{name}")
    params.set_param(f"facodi_ai.ci_xmlid.{name}", record.id)

env.cr.commit()
print("SEEDED_FACODI_AI_LEARNING_BRIDGE_UPGRADE_FIXTURE")
