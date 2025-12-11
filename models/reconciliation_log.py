# -*- coding: utf-8 -*-
from odoo import models, fields


class AutomatedReconciliationLog(models.Model):
    _name = 'automated.reconciliation.log'
    _description = 'Automated Reconciliation Log'

    config_id = fields.Many2one(
        'automated.reconciliation.config',
        string="Configuración relacionada",
        ondelete='cascade'
    )

    execution_date = fields.Datetime(
        string="Fecha ejecución",
        default=fields.Datetime.now
    )

    is_summary = fields.Boolean(
        string="Es resumen general",
        default=False
    )

    payment_ref = fields.Char(string="Referencia")
    encontrados = fields.Integer(string="Encontrados")
    coincidencias = fields.Integer(string="Coincidencias")
    conciliado = fields.Boolean(string="Conciliado")
    
    messages = fields.Text(string="Mensajes adicionales")


    log_ids = fields.One2many(
        'automated.reconciliation.log',
        'config_id',
        string='Historial de conciliaciones',
        readonly=True,
    )