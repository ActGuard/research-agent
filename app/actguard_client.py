from socket import timeout
import actguard
from app.config import settings

api_key = settings.actguard_api_key or None

actguard_client = actguard.Client(api_key=api_key, gateway_url=settings.actguard_gateway_url, debug=True, timeout_s=120, budget_timeout_s=120)