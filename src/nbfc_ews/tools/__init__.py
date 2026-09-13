from nbfc_ews.tools.bureau import GetBureauHistory
from nbfc_ews.tools.payment import GetPaymentBehaviour
from nbfc_ews.tools.registry import register

register(GetPaymentBehaviour())
register(GetBureauHistory())
