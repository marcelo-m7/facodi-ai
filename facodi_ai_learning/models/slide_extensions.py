from odoo import models


class SlideChannel(models.Model):
    _inherit = "slide.channel"

    def action_facodi_ai_analyze_learning(self):
        self.ensure_one()
        return self.env["facodi.ai.learning.job"]._enqueue_for_source(self)


class SlideSlide(models.Model):
    _inherit = "slide.slide"

    def action_facodi_ai_analyze_learning(self):
        self.ensure_one()
        return self.env["facodi.ai.learning.job"]._enqueue_for_source(self)
