from django.contrib import admin
from django.urls import path, include
from . import views as CalAppViews
from django.contrib.auth import views as auth_views
from django.http import HttpResponse

def Fix302(callback):
    def view(args):
        response = view.cb(args)
        if response.status_code == 302:
            return HttpResponse(status=302, content="/")
        return response
    view.cb = callback
    return view

urlpatterns = [
    path('', CalAppViews.Index, name="index"),
    path('register/', CalAppViews.Register, name="register"),
    path('login/', Fix302(auth_views.LoginView.as_view(template_name="CalendarApp/login.html")), name="login"),
    path('logout/', Fix302(auth_views.LogoutView.as_view(template_name="CalendarApp/logout.html")), name="logout"),
    path('calendaritem/', CalAppViews.CalendarItem, name="calendaritem")
]
