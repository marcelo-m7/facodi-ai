"""Verify the facodi_ai -> facodi_ai_learning ownership migration."""

params = env["ir.config_parameter"].sudo()

def stored_id(key):
    value = params.get_param(key)
    if not value:
        raise AssertionError(f"missing upgrade sentinel parameter: {key}")
    return int(value)

job_id = stored_id("facodi_ai.ci_bridge_job_id")
analysis_id = stored_id("facodi_ai.ci_bridge_analysis_id")
suggestion_id = stored_id("facodi_ai.ci_bridge_suggestion_id")

job = env["facodi.ai.learning.job"].browse(job_id).exists()
analysis = env["facodi.ai.learning.analysis"].browse(analysis_id).exists()
suggestion = env["facodi.ai.learning.suggestion"].browse(suggestion_id).exists()
if not job or not analysis or not suggestion:
    raise AssertionError("learning bridge rows did not survive the real upgrade")
if job.source_hash != "facodi-ai-learning-bridge-upgrade-sentinel":
    raise AssertionError("learning job identity changed during bridge migration")
if analysis.model_name != "legacy-test-model":
    raise AssertionError("learning analysis evidence changed during bridge migration")
if suggestion.rationale != "FACODI AI bridge upgrade sentinel suggestion":
    raise AssertionError("learning suggestion evidence changed during bridge migration")

if env["ir.module.module"].search(
    [("name", "=", "facodi_ai_learning"), ("state", "=", "installed")],
    limit=1,
).state != "installed":
    raise AssertionError("facodi_ai_learning is not installed after the split upgrade")

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
    expected_id = stored_id(f"facodi_ai.ci_xmlid.{name}")
    migrated = env.ref(f"facodi_ai_learning.{name}", raise_if_not_found=False)
    if not migrated:
        raise AssertionError(f"missing migrated XML ID facodi_ai_learning.{name}")
    if migrated.id != expected_id:
        raise AssertionError(
            f"XML ID facodi_ai_learning.{name} changed record identity "
            f"from {expected_id} to {migrated.id}"
        )
    if env.ref(f"facodi_ai.{name}", raise_if_not_found=False):
        raise AssertionError(f"legacy XML ID facodi_ai.{name} still owns bridge metadata")

remaining_core = env["ir.model.data"].sudo().search(
    [
        ("module", "=", "facodi_ai"),
        ("name", "ilike", "facodi_ai_learning"),
    ]
)
if remaining_core:
    raise AssertionError(
        "learning metadata still owned by facodi_ai: "
        + ", ".join(remaining_core.mapped("name"))
    )

print("VERIFIED_FACODI_AI_LEARNING_BRIDGE_UPGRADE")
