from django.shortcuts import render
from django.http import HttpResponse


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

def 