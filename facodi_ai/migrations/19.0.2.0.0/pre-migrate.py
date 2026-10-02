"""Transfer legacy FACODI AI learning metadata to facodi_ai_learning.

The model/table names are intentionally preserved. Transfer unclaimed legacy
external IDs to the bridge; let Odoo clean up legacy IDs already owned by the
bridge during the core upgrade, including noupdate cron records.
"""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1 FROM ir_model_data AS legacy
          JOIN ir_model_data AS bridge
            ON bridge.module = 'facodi_ai_learning'
           AND bridge.name = legacy.name
         WHERE legacy.module = 'facodi_ai'
           AND legacy.name LIKE '%facodi_ai_learning%'
           AND bridge.model != legacy.model
         LIMIT 1
        """
    )
    if cr.fetchone():
        raise RuntimeError("Conflicting FACODI AI learning XML ID models")

    cr.execute(
        """
        UPDATE ir_model_data AS legacy
           SET noupdate = FALSE
         WHERE legacy.module = 'facodi_ai'
           AND (
                legacy.name LIKE '%facodi_ai_learning%'
                OR legacy.name IN (
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
           AND EXISTS (
                SELECT 1 FROM ir_model_data AS bridge
                 WHERE bridge.module = 'facodi_ai_learning'
                   AND bridge.name = legacy.name
           )
        """
    )
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
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_data AS bridge
                 WHERE bridge.module = 'facodi_ai_learning'
                   AND bridge.name = ir_model_data.name
           )
        """
    )
