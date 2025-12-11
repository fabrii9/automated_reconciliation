# -*- coding: utf-8 -*-
{
    'name': "Conciliacion automatica",
    'license': 'AGPL-3',
    'summary': """
        Conciliacion automatica de cuentas bancarias
        """,
    'description': """
        Conciliacion automatica de cuentas bancarias
    """,
    'maintainer': 'Enzogonzalezdev',
    'author': "Fabrii9",
    'website': "https://www.printemps.com.ar",
    'category': 'Uncategorized',
    'version': '16.0.3.0.0',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/reconciliation_config_views.xml',
        'views/automated_reconciliation_log_view.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
