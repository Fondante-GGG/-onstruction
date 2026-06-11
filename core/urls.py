from django.contrib import admin
from django.urls import path, include
from core.yasg import urlpatterns_yasg

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('swagger/', include(urlpatterns_yasg)),
    path('api/building/', include('app.building.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)