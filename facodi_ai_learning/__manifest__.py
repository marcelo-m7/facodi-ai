{
    "name": "FACODI AI Learning",
    "summary": "Optional FACODI Learning integration for the reusable AI runtime",
    "version": "19.0.1.1.0",
    "category": "Website/eLearning",
    "author": "FACODI",
    "website": "https://facodi.com",
    "depends": ["facodi_ai", "facodi_learning"],
    "data": [
        "security/ir.model.access.csv",
        "data/learning_job_cron.xml",
        "views/learning_suggestion_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "application": False,
    "installable": True,
    "license": "LGPL-3",
}
