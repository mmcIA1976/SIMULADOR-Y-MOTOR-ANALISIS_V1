"""Explain funded-margin limits while preserving historical risk-budget labels."""
MINIMUM_TARGET_REASON = 'autonomous_minimum_tp_profit_unreachable'
MINIMUM_TARGET_EXPLANATION = (
    'El margen necesario para perseguir el beneficio mínimo supera la caja '
    'disponible con el apalancamiento permitido. No significa saldo cero.')
LEGACY_MINIMUM_TARGET_EXPLANATION = (
    'El objetivo mínimo de beneficio no cabe en los límites de caja, '
    'apalancamiento y pérdida máxima de la política histórica. No significa saldo cero.')


class SizingLimitError(ValueError):
    def __init__(self, details):
        super().__init__(MINIMUM_TARGET_REASON)
        self.details = details


def rejection_outcome(error):
    reason = str(error)
    return ('no_trade' if reason == MINIMUM_TARGET_REASON else 'no_cash',
            reason, getattr(error, 'details', None))


def explain_scan(scan):
    """Normalize archived labels for display, retaining the recorded status."""
    if scan.get('reason_code') == MINIMUM_TARGET_REASON:
        scan['recorded_status'] = scan.get('status')
        scan['status'] = 'no_trade'
        scan['status_label'] = 'Objetivo mínimo incompatible con los límites de asignación'
        sizing = ((scan.get('audit') or {}).get('gates') or {}).get('position_sizing') or {}
        scan['decision_explanation'] = (MINIMUM_TARGET_EXPLANATION
            if sizing.get('limiting_factor') == 'cash_and_leverage'
            else LEGACY_MINIMUM_TARGET_EXPLANATION)
    return scan
