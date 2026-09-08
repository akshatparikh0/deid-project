from rest_framework.views import exception_handler


def detail_exception_handler(exc, context):
    """Normalize every DRF error response to `{"detail": ..., ...}` per the
    API contract, regardless of which exception raised it."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    if isinstance(data, dict) and "detail" in data:
        response.data = data
    elif isinstance(data, dict):
        # e.g. serializer field errors: {"field": ["msg"]} -> flatten to one string
        parts = []
        for field, errors in data.items():
            if isinstance(errors, list):
                parts.append(f"{field}: {'; '.join(str(e) for e in errors)}")
            else:
                parts.append(f"{field}: {errors}")
        response.data = {"detail": " | ".join(parts) or "Invalid request."}
    elif isinstance(data, list):
        response.data = {"detail": "; ".join(str(e) for e in data)}
    else:
        response.data = {"detail": str(data)}
    return response
