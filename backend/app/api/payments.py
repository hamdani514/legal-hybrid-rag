"""
Card payments router (delegates to modules.payment).
All endpoints:
  - POST /api/payments/create-checkout-session
  - POST /api/payments/cancel-subscription
  - POST /api/payments/reactivate-subscription
  - GET  /api/payments/status
  - POST /api/payments/confirm
  - GET  /api/payments/config
  - POST /api/payments/webhook
"""

from modules.payment import router
from modules.payment.controller import _current_user, _is_paid, _stripe
from modules.payment.webhook import _extract_period_end, handle_checkout_completed

__all__ = ["router", "_current_user", "_is_paid", "_stripe", "_extract_period_end", "handle_checkout_completed"]
