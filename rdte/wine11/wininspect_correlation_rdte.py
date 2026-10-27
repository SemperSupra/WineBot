"""Synthetic RPC response-ID correlation oracle, not WinInspect production transport."""

class CorrelationError(Exception):
    pass

def correlate(request_id, response):
    if not isinstance(request_id, str) or not request_id:
        raise CorrelationError("invalid_request_id")
    if not isinstance(response, dict):
        raise CorrelationError("invalid_response")
    response_id = response.get("id")
    if not isinstance(response_id, str) or not response_id:
        raise CorrelationError("missing_response_id")
    if response_id != request_id:
        raise CorrelationError("response_id_mismatch")
    return response.get("result")
