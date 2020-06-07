from django.shortcuts import render
from django.http import HttpResponse
from .forms import UserRegisterForm, AddEventForm, AddTaskForm, EditEventForm, AddContactForm
from django.core.exceptions import PermissionDenied
from django.views.defaults import bad_request
from .CalendarItem import Task as CalAppTask, Event as CalAppEvent
from . import models as CalAppModels


# Each function will handle, where appropriate, more than one HTTP method

def CalendarItemsInDateRange(request):
    """Get a JSON list of calendar items within a date range. Omit range for all items. Supports GET."""
    pass

def Event(request):
    """Various operations on events - get info, update info, create new, delete. Supports GET, POST.
    Django does not support PUT or DELETE, at least easily, and so these are implemented with POST."""
    if request.user.is_authenticated :
        if request.method == "POST":
            if request.POST["req"] == "put":
                try:
                    form = AddEventForm(data=request.POST, user=request.user)
                    if form.is_valid():
                        CalAppEvent(form.cleaned_data, request.user).save()
                        return HttpResponse(status="302", content="/")
                    else:
                        return render(request, "CalendarApp/AddEvent.html", {'form': form})
                except:
                    return bad_request(request, "Failed")
            elif request.POST["req"] == "post":
                try:
                    obj = CalAppModels.Event.objects.get(pk=request.POST["pk"])
                    if not obj.owner == request.user:
                        raise PermissionDenied
                    form = EditEventForm(data=request.POST, user=request.user)
                    if form.is_valid():
                        pk = request.POST["pk"]
                        CalAppEvent(form.cleaned_data, request.user).save(pk=pk)
                        return HttpResponse(status="302", content="/")
                    else:
                        return render(request, "CalendarApp/AddEvent.html", {'form': form})
                except:
                    return bad_request(request, "Failed")
            elif request.POST["req"] == "delete":
                try:
                    obj = CalAppModels.Event.objects.get(pk=request.POST["pk"])
                    if not obj.owner == request.user:
                        raise PermissionDenied
                    obj.delete()
                    return HttpResponse(status="302", content="/")
                except:
                    return bad_request(request, "Failed")
        elif request.method == "GET":
            pass

    raise PermissionDenied

def Task(request):
    """Various operations on tasks - get info, update info, create new, delete. Supports GET, POST.
    Django does not support PUT or DELETE, at least easily, and so these are implemented with POST."""
    if request.user.is_authenticated:
        if request.method == "POST":
            if request.POST["req"] == "put":
                try:
                    form = AddTaskForm(data=request.POST, user=request.user)
                    if form.is_valid():
                        CalAppTask(form.cleaned_data, request.user).save()
                        return HttpResponse(status=302, content="/")
                    else:
                        return render(request, "CalendarApp/AddTask.html", {'form': form})
                except:
                    return bad_request(request, "Failed")
        elif request.method == "GET":
            pass
        elif request.method == "DELETE":
            pass

    raise PermissionDenied

def AddEvent(request):
    """Provides the Add Event form. Supports GET."""
    return render(request, "CalendarApp/AddEvent.html", {'form': AddEventForm(user=request.user)})

def AddTask(request):
    """Provides the Add Task form. Supports GET."""
    return render(request, "CalendarApp/AddTask.html", {'form': AddTaskForm(user=request.user)})


def Schedule(request):
    """Get the schedule for this calendar. Supports GET."""
    pass

def Index(request):
    """The index.html page that everyone expects. Supports GET."""
    if request.user.is_authenticated:
        events = CalAppModels.Event.objects.filter(owner=request.user)
    else:
        events = {}
    return render(request, "CalendarApp/index.html", {"events":events})

def Register(request):
    """Enables user to register an account. Supports Get and POST."""
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse(status=302, content="/")
        return render(request, "CalendarApp/register.html", {'form': form})
    return render(request, "CalendarApp/register.html", {"form": UserRegisterForm()})

def EditEvent(request):
    try:
        obj = CalAppModels.Event.objects.get(pk=request.GET["pk"])
        shares = CalAppModels.User_Event.objects.filter(event=obj)
        shared_users = {share.user for share in shares}
    except:
        return bad_request(request, "Failed")
    if request.user.is_authenticated \
            and obj.owner == request.user:
        form = EditEventForm(user=request.user, data={"text":obj.event_text,
                                                      "begin_datetime":obj.begin_datetime,
                                                      "end_datetime":obj.end_datetime,
                                                      "owner_importance":obj.owner_importance,
                                                      "shares":shared_users,
                                                      "pk":request.GET["pk"]})
        return render(request,
                       "CalendarApp/editevent.html",
                       {"form":form, "pk":request.GET["pk"], "type":request.GET["type"]})
    raise PermissionDenied

def Contacts(request):
    if request.user.is_authenticated:
        if request.method == "GET":
            contactObjects1 = CalAppModels.Contact.objects.filter(user1=request.user)
            contactObjects2 = CalAppModels.Contact.objects.filter(user2=request.user)
            contacts = {c.user2 for c in contactObjects1}.union({c.user1 for c in contactObjects2})
            form = AddContactForm()
            return render(request, "CalendarApp/contacts.html", {"contacts":contacts, "form":form})
        elif request.method == "POST":
            try:
                otherUser = CalAppModels.User.objects.get(username=request.POST["add_contact"])
            except:
                return bad_request(request, "Failed")
            if otherUser == request.user:
                return bad_request(request, "Failed")
            try:
                contactObj = CalAppModels.Contact.objects.filter(user1=request.user).get(user2=otherUser)
            except:
                try:
                    contactObj = CalAppModels.Contact.objects.filter(user2=request.user).get(user1=otherUser)
                except:
                    contactObj = CalAppModels.Contact(user1=request.user, user2=otherUser)
                    contactObj.save()
                    contactObjects1 = CalAppModels.Contact.objects.filter(user1=request.user)
                    contactObjects2 = CalAppModels.Contact.objects.filter(user2=request.user)
                    contacts = {c.user2 for c in contactObjects1}.union({c.user1 for c in contactObjects2})
                    form = AddContactForm()
                    return render(request, "CalendarApp/contacts.html", {"contacts": contacts, "form": form})
            return bad_request(request, "Failed")

    else:
        raise PermissionDenied

def DeleteContact(request):
    if request.user.is_authenticated:
        try:
            otherUser = CalAppModels.User.objects.get(pk=request.POST["pk"])
        except:
            return bad_request(request, "Failed")
        try:
            contactObj = CalAppModels.Contact.objects.filter(user1=request.user).get(user2=otherUser)
        except:
            try:
                contactObj = CalAppModels.Contact.objects.filter(user2=request.user).get(user1=otherUser)
            except:
                return bad_request(request, "Failed")
        contactObj.delete()
        contactObjects1 = CalAppModels.Contact.objects.filter(user1=request.user)
        contactObjects2 = CalAppModels.Contact.objects.filter(user2=request.user)
        contacts = {c.user2 for c in contactObjects1}.union({c.user1 for c in contactObjects2})
        form = AddContactForm()
        return render(request, "CalendarApp/contacts.html", {"contacts": contacts, "form": form})
    else:
        raise PermissionDenied