from django.urls import path

from . import views


urlpatterns = [
    path('', views.home, name='home'),
    path('signin/', views.do_signin, name='signin'),
    path('logout/', views.do_logout, name='logout'),
    path('about/', views.about, name='about'),
]
