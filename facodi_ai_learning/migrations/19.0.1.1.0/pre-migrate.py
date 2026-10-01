"""Reconcile duplicate AI learning jobs before adding strict source uniqueness.

The original three-column UNIQUE constraint did not protect course or content jobs
because exactly one source column is NULL and PostgreSQL UNIQUE treats NULL values
as distinct. Preserve analysis provenance by moving analyses to one canonical job
before removing duplicate job rows.
"""


def migrate(cr, version):
    ranking = """
        SELECT
            id,
            FIRST_VALUE(id) OVER (
                PARTITION BY source_channel_id, source_slide_id, source_hash
                ORDER BY
                    CASE state
                        WHEN 'completed' THEN 0
                        WHEN 'pending' THEN 1
                        WHEN 'failed' THEN 2
                        ELSE 3
                    END,
                    id
            ) AS keep_id,
            COUNT(*) OVER (
                PARTITION BY source_channel_id, source_slide_id, source_hash
            ) AS duplicate_count
        FROM facodi_ai_learning_job
    """

    cr.execute(
        f"""
        WITH ranked AS ({ranking})
        UPDATE facodi_ai_learning_analysis AS analysis
           SET job_id = ranked.keep_id
          FROM ranked
         WHERE ranked.duplicate_count > 1
           AND analysis.job_id = ranked.id
           AND ranked.id <> ranked.keep_id
        """
    )

    cr.execute(
        f"""
        WITH ranked AS ({ranking})
        DELETE FROM facodi_ai_learning_job AS job
         USING ranked
         WHERE ranked.duplicate_count > 1
           AND job.id = ranked.id
           AND ranked.id <> ranked.keep_id
        """
    )
