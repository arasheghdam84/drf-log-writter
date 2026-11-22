from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView


class LoginView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        return Response({"token": "issued-token", "user": {"username": request.data.get("username")}})


class UploadView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        return Response({"received": sorted(request.FILES)}, status=201)


def boom(request):
    raise ValueError("boom")


def plain(request):
    return JsonResponse({"ok": True})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/login/", LoginView.as_view()),
    path("api/upload/", UploadView.as_view()),
    path("plain/", plain),
    path("boom/", boom),
]
