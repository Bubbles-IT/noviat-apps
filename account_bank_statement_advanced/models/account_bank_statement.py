# -*- coding: utf-8 -*-
# Copyright 2009-2018 Noviat.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from lxml import etree
import time

from odoo import api, models, _


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    @api.one
    @api.depends('line_ids.journal_entry_ids')
    def _check_lines_reconciled(self):
        """
        Replacement of this method without inherit.

        Standard account module logic:
        self.all_lines_reconciled = all(
            [line.journal_entry_ids.ids
             or line.account_id.id for line in self.line_ids])
        """
        self.all_lines_reconciled = True
        for line in self.line_ids:
            if (line.amount and not line.journal_entry_ids
                    and not line.account_id):
                self.all_lines_reconciled = False
                break

    @api.model
    def fields_view_get(self, view_id=None, view_type=False,
                        toolbar=False, submenu=False):
        """
        Hide 'Reset to New' button.
        We use fields_view_get in stead of xml inherit since older
        databases may have been migrated without the view that
        adds the 'button_draft' button.
        """
        res = super(AccountBankStatement, self).fields_view_get(
            view_id=view_id, view_type=view_type,
            toolbar=toolbar, submenu=submenu)
        if view_type == 'form':
            form = etree.XML(res['arch'])
            for node in form.xpath("//button[@name='button_draft']"):
                node.set('modifiers', '{"invisible": true}')
            res['arch'] = etree.tostring(form)
        return res

    @api.multi
    def button_cancel(self):
        """
        Replace the account module button_cancel to allow
        cancel statements while preserving associated moves.
        """
        self.state = 'open'
        return True

    @api.multi
    def button_confirm_bank(self):
        """
        Some of the function in this method are handled (differently) by the
        CODA processing hence we bypass those here.
        """
        coda_statements = self.filtered(lambda r: r.coda_id)
        non_coda_statements = self - coda_statements
        super(AccountBankStatement, non_coda_statements).button_confirm_bank()

        coda_statements._balance_check()
        coda_statements = coda_statements.filtered(
            lambda r: r.state == 'open')
        moves = coda_statements.mapped('line_ids').mapped('journal_entry_ids')
        unposted = moves.filtered(lambda r: r.state == 'draft')
        unposted.post()
        for statement in coda_statements:
            statement.message_post(
                body=_('Statement %s confirmed, journal items were created.'
                       ) % (statement.name,))
        coda_statements.write({
            'state': 'confirm',
            'date_done': time.strftime("%Y-%m-%d %H:%M:%S")})
        return True

    @api.multi
    def automatic_reconcile(self):
        reconcile_note = ''
        for st in self:
            reconcile_note = self._automatic_reconcile(
                reconcile_note=reconcile_note)
        if reconcile_note:
            module = __name__.split('addons.')[1].split('.')[0]
            result_view = self.env.ref(
                '%s.bank_statement_automatic_reconcile_result_view_form'
                % module)
            return {
                'name': _("Automatic Reconcile remarks:"),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'bank.statement.automatic.reconcile.result.view',
                'view_id': result_view.id,
                'target': 'new',
                'context': dict(self._context, note=reconcile_note),
                'type': 'ir.actions.act_window',
            }
        else:
            return True

    def _automatic_reconcile(self, reconcile_note):
        """
        Placeholder for modules that implement automatic reconciliation (e.g.
        l10n_be_coda_advanced) as a preprocessing step before entering
        into the standard addons javascript reconciliation screen.
        This screen has also an 'auto_reconcile' option but unfortunately
        - too much hardcoded
        - risks on wrong reconciles
        - too late in the process (the javascript screen is not usable for
          lorge statements hence pre-processing is required)
        """
        self.ensure_one()
        return reconcile_note
