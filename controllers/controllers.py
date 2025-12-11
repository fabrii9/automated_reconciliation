# -*- coding: utf-8 -*-
# from odoo import http


# class AutomatedReconciliation(http.Controller):
#     @http.route('/automated_reconciliation/automated_reconciliation', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/automated_reconciliation/automated_reconciliation/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('automated_reconciliation.listing', {
#             'root': '/automated_reconciliation/automated_reconciliation',
#             'objects': http.request.env['automated_reconciliation.automated_reconciliation'].search([]),
#         })

#     @http.route('/automated_reconciliation/automated_reconciliation/objects/<model("automated_reconciliation.automated_reconciliation"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('automated_reconciliation.object', {
#             'object': obj
#         })
