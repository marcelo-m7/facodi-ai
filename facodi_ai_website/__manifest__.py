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
    "application": False,
    "installable": True,
    "license": "LGPL-3",
}
