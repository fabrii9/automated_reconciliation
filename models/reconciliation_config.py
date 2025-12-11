# models/automated_reconciliation_config.py

from odoo import models, fields, api
import xmlrpc.client
import logging
from datetime import datetime
import re
from odoo.exceptions import UserError
import time

_logger = logging.getLogger(__name__)


class AutomatedReconciliationConfig(models.Model):
    _name = 'automated.reconciliation.config'
    _description = 'Configuración para conciliación automática'

    name = fields.Char(string="Nombre de configuración", required=True)
    url = fields.Char(string="URL", required=True)
    db = fields.Char(string="Base de datos", required=True)
    username = fields.Char(string="Usuario", required=True)
    password = fields.Char(string="Contraseña", required=True)
    journal_filter = fields.Integer(string="Filtro de Diario (ID)", required=True)
    target_account_id = fields.Integer(string="Cuenta contable objetivo (ID)", required=True)

    target_date = fields.Date(string="Fecha de conciliación inicio", required=True)
    target_date_end = fields.Date(string="Fecha de conciliación fin", required=True)

    tolerance = fields.Float(string="Tolerancia", digits=(12, 4), required=True)

    account_credit_id = fields.Integer(
        string="Cuenta de haber (ID)",
        help="ID de la cuenta contable que tendrá el movimiento en el haber",
        required=True
    )
    account_debit_id = fields.Integer(
        string="Cuenta de debe (ID)",
        help="ID de la cuenta contable que tendrá el movimiento en el debe",
        required=True
    )

    log_ids = fields.One2many('automated.reconciliation.log', 'config_id', string="Logs")

    payment_ref = fields.Boolean(
        string="Referencia",
        default=True)
    date = fields.Boolean(
        string="Fecha",
        default=True)
    amount = fields.Boolean(
        string="Monto",
        default=True)
    account = fields.Boolean(
        string="Cuenta",
        default=True)

    def action_execute_reconciliation(self):
        for config in self:
            try:
                logs = config._run_script(
                    config.url,
                    config.db,
                    config.username,
                    config.password,
                    config.journal_filter,
                    config.target_account_id,
                    config.target_date.strftime('%Y-%m-%d'),
                    config.target_date_end.strftime('%Y-%m-%d'),
                    config.tolerance
                )

                total_lines = len(logs['lines'])
                conciliados = 0
                no_conciliados = 0

                # Primero, registro resumen general
                self.env['automated.reconciliation.log'].create({
                    'config_id': config.id,
                    'is_summary': True,
                    'messages': f"Se encontraron {total_lines} líneas bancarias para procesar."
                })

                # Registro individual por línea
                for line in logs['lines']:
                    conciliado = line['conciliado']
                    if conciliado:
                        conciliados += 1
                    else:
                        no_conciliados += 1

                    self.env['automated.reconciliation.log'].create({
                        'config_id': config.id,
                        'payment_ref': line['payment_ref'],
                        'encontrados': line['encontrados'],
                        'coincidencias': line['coincidencias'],
                        'conciliado': conciliado,
                        'messages': line['message']
                    })

                # Finalmente, resumen del resultado
                self.env['automated.reconciliation.log'].create({
                    'config_id': config.id,
                    'is_summary': True,
                    'messages': f"Conciliados: {conciliados}, No Conciliados: {no_conciliados}."
                })

                # Notificación final
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f"Conciliados: {conciliados}, No Conciliados: {no_conciliados}",
                        'type': 'success',
                        'sticky': False,
                    }
                }

            except xmlrpc.client.ProtocolError as e:
                # Manejo específico para errores HTTP desde XML-RPC
                if getattr(e, "errcode", None) == 429:
                    error_message = (
                        "El servidor remoto devolvió 429 Too Many Requests "
                        "incluso después de reintentar. Probá de nuevo en unos minutos."
                    )
                else:
                    error_message = f"Error HTTP al ejecutar conciliación (código {e.errcode}): {e}"

                self.env['automated.reconciliation.log'].create({
                    'config_id': config.id,
                    'is_summary': True,
                    'messages': error_message,
                })

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': error_message,
                        'type': 'danger',
                        'sticky': True,
                    }
                }

            except Exception as e:
                error_message = f"Error al ejecutar conciliación: {str(e)}"
                self.env['automated.reconciliation.log'].create({
                    'config_id': config.id,
                    'is_summary': True,
                    'messages': error_message,
                })

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': error_message,
                        'type': 'danger',
                        'sticky': False,
                    }
                }

    def action_open_last_log(self):
        self.ensure_one()
        last_log = self.log_ids[:1]  # ya están ordenados por create_date desc
        if not last_log:
            raise UserError("No hay logs disponibles.")

        return {
            'type': 'ir.actions.act_window',
            'name': 'Último Log',
            'res_model': 'automated.reconciliation.log',
            'view_mode': 'form',
            'res_id': last_log.id,
            'view_id': self.env.ref('tu_modulo.view_automated_reconciliation_log_modal').id,  # reemplazá por el nombre correcto del módulo
            'target': 'new',
        }

    def _run_script(self, url, db, username, password, journal_filter,
                    target_account_id, target_date, target_date_end, tolerance):
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        uid = common.authenticate(db, username, password, {})
        if not uid:
            raise Exception("No se pudo autenticar")

        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

        def api_call(model_name, func, args, kwargs=None):
            """
            Wrapper para execute_kw con manejo de HTTP 429 (Too Many Requests)
            y reintentos con backoff incremental.
            """
            kwargs = kwargs or {}
            max_retries = 5
            base_backoff = 2  # segundos

            attempt = 0
            while True:
                try:
                    return models.execute_kw(
                        db,
                        uid,
                        password,
                        model_name,
                        func,
                        args,
                        kwargs,
                    )

                except xmlrpc.client.ProtocolError as e:
                    # Rate limit (429) → reintentamos con backoff
                    if getattr(e, "errcode", None) == 429 and attempt < max_retries:
                        attempt += 1
                        delay = base_backoff * attempt
                        _logger.warning(
                            "HTTP 429 en conciliación automática "
                            "(modelo %s, método %s). Reintento %s/%s en %ss",
                            model_name,
                            func,
                            attempt,
                            max_retries,
                            delay,
                        )
                        time.sleep(delay)
                        continue

                    # Si agotamos reintentos o es otro error HTTP, relanzamos
                    raise

                except Exception:
                    # Otros errores se relanzan tal cual
                    raise

        def extract_numeric_ref(ref_value):
            if not ref_value:
                return ref_value
            ref_value = ref_value.strip()
            match = re.search(r'\d+', ref_value)
            return match.group(0) if match else ref_value

        domain = [
            "&", "&",
            ["journal_id", "=", journal_filter],
            ["is_reconciled", "=", False],
            ["date", ">=", target_date],
            ["date", "<=", target_date_end],
        ]

        bank_lines = api_call('account.bank.statement.line', 'search_read', [domain], {
            'fields': ['id', 'payment_ref', 'date', 'amount']
        })

        lines = []

        for line in bank_lines:
            diario_id = line['id']
            date_val = line['date']
            payment_ref_val = line['payment_ref']
            amount_val = line['amount']

            domain_candidato = [
                ("account_id", "=", target_account_id),
                ("date", "=", date_val),
            ]
            numeric_ref = False
            if self.payment_ref:
                numeric_ref = extract_numeric_ref(payment_ref_val)
            if numeric_ref:
                domain_candidato.append(("ref", "=", numeric_ref))

            candidatos = api_call('account.move.line', 'search_read', [domain_candidato], {
                'fields': ['id', 'ref', 'date', 'amount_residual', 'account_id', 'partner_id'],
            })

            matching = [c for c in candidatos if abs(c.get('amount_residual', 0) - amount_val) <= tolerance]

            conciliado = False
            mensaje = f"Línea {diario_id} NO reconciliada."
            date = datetime.strptime(date_val, '%Y-%m-%d').date()
            formatted_date = date.strftime('%d/%m/%Y')

            if len(matching) == 1:
                linea = api_call('account.bank.statement.line', 'search_read', [[("id", "=", diario_id)]])
                apunte_contable = api_call('account.move', 'search_read', [[('id', '=', linea[0]['move_id'][0])]])
                line_to_assign = 0
                # TODO: Agregar ID del recibo de pago.
                for l in apunte_contable[0]['line_ids']:
                    line_to_assign = 0
                    try:
                        l_id = api_call('account.move.line', 'search_read', [[('id', '=', l)]])
                        if l_id[0]['debit'] > 0.0:
                            dicttionary = {
                                'partner_id': candidatos[0]['partner_id'][0],
                                'account_id': self.account_debit_id,
                            }
                            line_to_assign = 1
                            api_call('account.move.line', 'write', [[l], dicttionary])
                            break

                        elif l_id[0]['debit'] < 0.0:
                            dicttionary = {
                                'partner_id': candidatos[0]['partner_id'][0],
                                'account_id': self.account_credit_id
                            }
                            api_call('account.move.line', 'write', [[l], dicttionary])
                            line_to_assign = 0
                            break

                        elif l_id[0]['credit'] > 0.0:
                            dicttionary = {
                                'account_id': self.account_credit_id,
                                'name': f'Pago de cliente ${l_id[0]["credit"]} - {candidatos[0]["partner_id"][1]} - ',
                                'partner_id': candidatos[0]['partner_id'][0],
                            }
                            line_to_assign = 0
                            api_call('account.move.line', 'write', [[l], dicttionary])
                            break

                        elif l_id[0]['credit'] < 0.0:
                            dicttionary = {
                                'account_id': self.account_debit_id,
                                'name': f'Pago de cliente ${l_id[0]["credit"]} - {candidatos[0]["partner_id"][1]} - ',
                                'partner_id': candidatos[0]['partner_id'][0],
                            }
                            line_to_assign = 1
                            api_call('account.move.line', 'write', [[l], dicttionary])
                            break

                    except Exception as e:
                        _logger.error(f"Error al procesar la línea contable: {str(e)}")

                try:
                    lineas_move = apunte_contable[0]['line_ids']
                    for linea_id in lineas_move:
                        move_line = api_call('account.move.line', 'search_read', [[('id', '=', linea_id)]])
                        if line_to_assign == 1:
                            move_line_write = api_call(
                                'account.move.line',
                                'write',
                                [[lineas_move[line_to_assign]],
                                 {
                                     'account_id': self.account_credit_id,
                                     'partner_id': matching[0]['partner_id'][0],
                                     'name': f'Pago de cliente ${l_id[0]["debit"]} - {matching[0]["partner_id"][1]} - {formatted_date}'
                                 }]
                            )
                            line_to_assign = 0
                            pass
                        if move_line and move_line[0]['account_id'][0] == matching[0]['account_id'][0]:
                            try:
                                api_call('account.move.line', 'reconcile', [[linea_id, matching[0]['id']]])
                                break
                            except Exception as e:
                                _logger.info("Error al reconciliar: Todo bien, si concilió")

                    api_call('account.bank.statement.line', 'write', [[diario_id], {"is_reconciled": True}])
                except Exception as e:
                    _logger.error(f"Error al cerrar conciliación: {str(e)}")
                conciliado = True
                mensaje = f"Línea {diario_id} reconciliada."

            lines.append({
                'payment_ref': payment_ref_val,
                'encontrados': len(candidatos),
                'coincidencias': len(matching),
                'conciliado': conciliado,
                'message': mensaje
            })

        return {'lines': lines}
