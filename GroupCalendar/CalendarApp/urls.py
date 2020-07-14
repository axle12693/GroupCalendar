from django.urls import path
from . import views as cal_app_views
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from .forms import RepetitionForm
from django.shortcuts import render


def fix_302(callback):
    def view(args):
        response = view.cb(args)
        if response.status_code == 302:
            return HttpResponse(status=302, content="/")
        return response
    view.cb = callback
    return view


urlpatterns = [
    path('', cal_app_views.Index, name="index"),
    path('register/', cal_app_views.Register, name="register"),
    path('login/', fix_302(auth_views.LoginView.as_view(template_name="CalendarApp/login.html")), name="login"),
    path('logout/', fix_302(auth_views.LogoutView.as_view(template_name="CalendarApp/logout.html")), name="logout"),
    path('addevent/', cal_app_views.AddEvent, name="addevent"),
    path('addtask/', cal_app_views.AddTask, name="addtask"),
    path('event/', cal_app_views.Event, name="event"),
    path('task/', cal_app_views.Task, name="task"),
    path('editevent/', cal_app_views.EditEvent, name="editevent"),
    path('edittask/', cal_app_views.EditTask, name="edittask"),
    path('contacts/', cal_app_views.Contacts, name="contacts"),
    path('deletecontact/', cal_app_views.DeleteContact, name="deletecontact"),
    path('acceptcontact/', cal_app_views.AcceptContact, name="acceptcontact"),
    path('calsharetoggle/', cal_app_views.CalShareToggle, name='calsharetoggle'),
    path('calviewtoggle/', cal_app_views.CalViewToggle, name='calviewtoggle'),
    path('getrepeatform/',
         lambda request: render(request,
                                "CalendarApp/repeatForm.html",
                                {"repeatForm": RepetitionForm()}),
         name='getrepeatform'),
    path('schedule/', cal_app_views.Schedule, name='schedule')
]
