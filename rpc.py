import base64
import requests
from flask import current_app


class AnopeError(Exception):
    def __init__(self, message, code=None):
        self.message = message
        self.code = code
        super().__init__(message)


def rpc(method, *params):
    url = current_app.config["ANOPE_RPC_URL"]
    token = current_app.config["ANOPE_RPC_TOKEN"]
    encoded = base64.b64encode(token.encode()).decode()

    try:
        resp = requests.post(
            url,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": method,
                "params": list(params),
            },
            headers={"Authorization": f"Bearer {encoded}"},
            timeout=5,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise AnopeError("Could not connect to Anope services")
    except requests.exceptions.Timeout:
        raise AnopeError("Anope services timed out")

    data = resp.json()

    if "error" in data:
        raise AnopeError(data["error"].get("message", "Unknown error"), data["error"].get("code"))

    return data.get("result")
