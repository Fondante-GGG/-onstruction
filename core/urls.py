from django.contrib import admin
from django.urls import path, include
from core.yasg import urlpatterns_yasg

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/building/', include('app.building.urls')),
]

urlpatterns += urlpatterns_yasg

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
