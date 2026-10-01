"""Transfer legacy FACODI AI learning metadata to facodi_ai_learning.

The model/table names are intentionally preserved. This migration only moves
external-ID ownership so the new bridge addon updates the existing records
instead of recreating cron, views, ACLs, model metadata, or field metadata.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_model_data
           SET module = 'facodi_ai_learning'
         WHERE module = 'facodi_ai'
           AND (
                name LIKE '%facodi_ai_learning%'
                OR name IN (
                    'ir_cron_facodi_ai_learning_jobs',
                    'view_facodi_ai_learning_suggestion_list',
                    'view_facodi_ai_learning_suggestion_form',
                    'action_facodi_ai_learning_suggestions',
                    'menu_facodi_ai_learning_suggestions',
                    'access_facodi_ai_learning_job_manager',
                    'access_facodi_ai_learning_analysis_manager',
                    'access_facodi_ai_learning_suggestion_manager'
                )
           )
        """
    )
