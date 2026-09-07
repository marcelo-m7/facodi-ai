from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.facodi_ai.services.errors import FacodiAIError


class FacodiAIWebsiteController(http.Controller):
    @http.route(
        "/facodi_ai/website/translate",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
        website=True,
    )
    def translate_website_page(
        self,
        page_view_id,
        target_lang,
        mode,
        units,
    ):
        if not request.env.user.has_group("website.group_website_designer"):
            raise AccessError(_("Website editor access is required to use FACODI AI translation."))
        try:
            return request.env["facodi.ai.website.translation_service"].translate_page(
                website=request.website,
                page_view_id=page_view_id,
                target_lang=target_lang,
                mode=mode,
                units=units,
            )
        except FacodiAIError as error:
            raise UserError(
                _("FACODI AI Website translation failed: %(message)s", message=str(error))
            ) from error
