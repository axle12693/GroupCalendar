from django.contrib import admin
from django.urls import path, include
from . import views as CalAppViews
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from .forms import RepetitionForm
from django.shortcuts import render



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
    path('addevent/', CalAppViews.AddEvent, name="addevent"),
    path('addtask/', CalAppViews.AddTask, name="addtask"),
    path('event/', CalAppViews.Event, name="event"),
    path('task/', CalAppViews.Task, name="task"),
    path('editevent/', CalAppViews.EditEvent, name="editevent"),
    path('edittask/', CalAppViews.EditTask, name="edittask"),
    path('contacts/', CalAppViews.Contacts, name="contacts"),
    path('deletecontact/', CalAppViews.DeleteContact, name="deletecontact"),
    path('acceptcontact/', CalAppViews.AcceptContact, name="acceptcontact"),
    path('calsharetoggle/', CalAppViews.CalShareToggle, name='calsharetoggle'),
    path('calviewtoggle/', CalAppViews.CalViewToggle, name='calviewtoggle'),
    path('getrepeatform/',
         lambda request: render(request,
                                "CalendarApp/repeatForm.html",
                                {"repeatForm": RepetitionForm()}),
         name='getrepeatform'),
    path('schedule/', CalAppViews.Schedule, name='schedule')
]
