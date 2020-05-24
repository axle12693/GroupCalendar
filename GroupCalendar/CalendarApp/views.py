from django.shortcuts import render
from django.http import HttpResponse
from .forms import UserRegisterForm


# Each function will handle, where appropriate, more than one HTTP method

def CalendarItemsInDateRange(request):
    """Get a JSON list of calendar items within a date range. Omit range for all items. Supports GET."""
    pass


def CalendarItem(request):
    """Various operations on calendar items - get info, update info, create new, delete. Supports GET, POST, PUT, DELETE."""
    pass


def Schedule(request):
    """Get the schedule for this calendar. Supports GET."""
    pass

def Index(request):
    """The index.html page that everyone expects. Supports GET."""
    CreateUserForm = UserRegisterForm()
    return render(request, "CalendarApp/index.html", {'CreateUserForm': CreateUserForm})

def Register(request):
    """Enables user to register an account. Supports POST."""
    # if request.method == 'POST':
    #     form =