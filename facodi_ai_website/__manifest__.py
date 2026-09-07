{
    "name": "FACODI AI Website",
    "summary": "AI-assisted translation in the standard Odoo Website editor",
    "version": "19.0.1.0.0",
    "category": "Website/Website",
    "author": "Marcelo Santos",
    "website": "https://facodi.pt",
    "depends": ["website", "facodi_ai"],
    "data": [
        "data/profile_data.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "website.website_builder_assets": [
            "facodi_ai_website/static/src/builder/**/*",
        ],
        "web.assets_unit_tests": [
            "facodi_ai_website/static/src/builder/facodi_ai_translation_plugin.js",
            "facodi_ai_website/static/tests/**/*",
        ],
    },
    "application": False,
    "installable": True,
    "license": "LGPL-3",
}
