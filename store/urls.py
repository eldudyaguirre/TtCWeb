from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signin/', views.do_signin, name='signin'),
    path('logout/', views.do_logout, name='logout'),
    path('signup/', views.do_signup, name='signup'),
    path('success-signup/', views.success_signup, name='success_signup'),
    path('about/', views.about, name='about'),
    #path('sign-in/', views.signinnow, name='sign-in'),
    #path('sign-up/', views.signupnow, name='sign-up'),

]

