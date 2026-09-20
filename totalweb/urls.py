"""
URL configuration for TotalCounts.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings


handler404 = 'store.views.error_404'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('store.urls')),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
