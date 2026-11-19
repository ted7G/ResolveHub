from .views import healthz


class HealthCheckMiddleware:
    """
    Answers /healthz before any other middleware runs.

    Container health checks call the app on its internal address (for
    example http://127.0.0.1:8000), which is neither an allowed host nor
    HTTPS. Handling the path here keeps the probe working without loosening
    ALLOWED_HOSTS or the HTTPS redirect for every other request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info == "/healthz":
            return healthz(request)
        return self.get_response(request)
