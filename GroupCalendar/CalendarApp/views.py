from django.shortcuts import render
from django.http import HttpResponse
from .forms import UserRegisterForm
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from django.views.defaults import bad_request
import json
from .CalendarItem import Task, Event


# Each function will handle, where appropriate, more than one HTTP method

def CalendarItemsInDateRange(request):
    """Get a JSON list of calendar items within a date range. Omit range for all items. Supports GET."""
    pass


def CalendarItem(request):
    """Various operations on calendar items - get info, update info, create new, delete. Supports GET, POST, PUT, DELETE."""
    if request.user.is_authenticated:
        if request.method == "PUT":
            try:
                if request.body.type["type"] == "task":
                    Task(data, request.user).save()
                elif data["type"] == "event":
                    Event(data, request.user).save()
            except:
                return bad_request(request, "Failed")

    raise PermissionDenied


def Schedule(request):
    """Get the schedule for this calendar. Supports GET."""
    pass

def Index(request):
    """The index.html page that everyone expects. Supports GET."""
    CreateUserForm = UserRegisterForm()
    return render(request, "CalendarApp/index.html", {'CreateUserForm': CreateUserForm})

def Register(request):
    """Enables user to register an account. Supports Get and POST."""
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse(status=302, content="/")
        return render(request, "CalendarApp/register.html", {'form': form})
    return render(request, "CalendarApp/register.html", {"form": UserRegisterForm()})