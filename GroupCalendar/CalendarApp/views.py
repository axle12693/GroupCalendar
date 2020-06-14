from django.shortcuts import render
from django.http import HttpResponse
from .forms import UserRegisterForm, AddEventForm, AddTaskForm, EditEventForm, AddContactForm, EditSharedEventForm
from django.core.exceptions import PermissionDenied
from django.views.defaults import bad_request
from .CalendarItem import Task as CalAppTask, Event as CalAppEvent
from . import models as CalAppModels
from copy import deepcopy


# Each function will handle, where appropriate, more than one HTTP method

def _get_all_contacts(request):
    contactObjects1 = CalAppModels.Contact.objects.filter(user1=request.user, state="accepted")
    contactObjects2 = CalAppModels.Contact.objects.filter(user2=request.user, state="accepted")
    contacts = {c.user2 for c in contactObjects1}.union({c.user1 for c in contactObjects2})
    invited1Objects = CalAppModels.Contact.objects.filter(user1=request.user, state="invited")
    invited1 = {c.user2 for c in invited1Objects}
    invited2Objects = CalAppModels.Contact.objects.filter(user2=request.user, state="invited")
    invited2 = {c.user1 for c in invited2Objects}
    return contacts, invited1, invited2

def _render_contacts_form(request):
    contacts, invited1, invited2 = _get_all_contacts(request)
    cal_shared_with = CalAppModels.Cal_Share.objects.filter(sharer=request.user)
    cal_users_shared_with = {cal_share.sharee for cal_share in cal_shared_with}
    cal_shared_from = CalAppModels.Cal_Share.objects.filter(sharee=request.user)
    cal_users_shared_from = {cal_share.sharer for cal_share in cal_shared_from}
    viewed = ((share.sharer.pk, share.status) for share in cal_shared_from)
    form = AddContactForm()
    return render(request, "CalendarApp/contacts.html", {"contacts": contacts,
                                                         "invited1": invited1,
                                                         "invited2": invited2,
                                                         "form": form,
                                                         "shared_with_them": cal_users_shared_with,
                                                         "shared_with_me": cal_users_shared_from,
                                                         "viewed": viewed})

def _unshare_all_between_contacts(user1, user2):
    # Unshare tasks shared between them
    try:
        tasksOwnedBy1 = CalAppModels.Task.objects.filter(owner=user1)
        tasksToUnshare = CalAppModels.User_Task.objects.filter(user=user2).filter(task__in=tasksOwnedBy1)
        tasksToUnshare.delete()
    except:
        pass
    try:
        tasksOwnedBy2 = CalAppModels.Task.objects.filter(owner=user2)
        tasksToUnshare = CalAppModels.User_Task.objects.filter(user=user1).filter(task__in=tasksOwnedBy2)
        tasksToUnshare.delete()
    except:
        pass
    # Unshare events shared between them
    try:
        eventsOwnedBy1 = CalAppModels.Task.objects.filter(owner=user1)
        eventsToUnshare = CalAppModels.User_Event.objects.filter(user=user2).filter(event__in=eventsOwnedBy1)
        eventsToUnshare.delete()
    except:
        pass
    try:
        eventsOwnedBy2 = CalAppModels.Task.objects.filter(owner=user2)
        eventsToUnshare = CalAppModels.User_Event.objects.filter(user=user1).filter(event__in=eventsOwnedBy2)
        eventsToUnshare.delete()
    except:
        pass


def CalendarItemsInDateRange(request):
    """Get a JSON list of calendar items within a date range. Omit range for all items. Supports GET."""
    pass


def Event(request):
    """Various operations on events - get info, update info, create new, delete. Supports GET, POST.
    Django does not support PUT or DELETE, at least easily, and so these are implemented with POST."""
    if request.user.is_authenticated:
        if request.method == "POST":
            if request.POST["req"] == "put":
                # try:
                form = AddEventForm(data=request.POST, user=request.user)
                if form.is_valid():
                    CalAppEvent(form.cleaned_data, request.user).save()
                    return HttpResponse(status="302", content="/")
                else:
                    return render(request, "CalendarApp/AddEvent.html", {'form': form})
                # except:
                #     return bad_request(request, "Failed")
            elif request.POST["req"] == "post":
                try:
                    obj = CalAppModels.Event.objects.get(pk=request.POST["pk"])
                    if not obj.owner == request.user:
                        shares = CalAppModels.User_Event.objects.filter(user=request.user).filter(event=obj)
                        if shares:
                            form = EditSharedEventForm(data=request.POST)
                            if form.is_valid():
                                share = shares.first()
                                share.importance = request.POST["importance"]
                                share.save()
                                return HttpResponse(status="302", content="/")
                            else:
                                return render(request, "CalendarApp/AddEvent.html", {'form': form, "noDelete": 1})
                        raise PermissionDenied
                    form = EditEventForm(data=request.POST, user=request.user)
                    if form.is_valid():
                        pk = request.POST["pk"]
                        CalAppEvent(form.cleaned_data, request.user).save(pk=pk)
                        return HttpResponse(status="302", content="/")
                    else:
                        return render(request, "CalendarApp/AddEvent.html", {'form': form})
                except CalAppModels.Event.DoesNotExist:
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
        eventsOwned = CalAppModels.Event.objects.filter(owner=request.user)
        shares = CalAppModels.User_Event.objects.filter(user=request.user)
        eventsSharedSet = {share.event for share in shares}
        eventPKs = {event.pk for event in eventsSharedSet}
        eventsShared = CalAppModels.Event.objects.filter(pk__in=eventPKs)
        calendars_shared_with_me = CalAppModels.Cal_Share.objects.filter(sharee=request.user, status="viewed")
        users_sharing_calendars_with_me = {calendar.sharer for calendar in calendars_shared_with_me}
        events_in_calendars_shared_with_me = set()
        for user in users_sharing_calendars_with_me:
            events = CalAppModels.Event.objects.filter(owner=user)
            if events_in_calendars_shared_with_me:
                events_in_calendars_shared_with_me = events_in_calendars_shared_with_me.union(events)
            else:
                events_in_calendars_shared_with_me = deepcopy(events)

        events_in_calendars_shared_with_me = events_in_calendars_shared_with_me.difference(eventsShared)
    else:
        eventsOwned = {}
        eventsShared = {}
        events_in_calendars_shared_with_me = {}
    return render(request, "CalendarApp/index.html", {"eventsOwned": eventsOwned,
                                                      "eventsShared": eventsShared,
                                                      "eventsInViewedCalendars": events_in_calendars_shared_with_me})


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
    if request.user.is_authenticated:
        if obj.owner == request.user:
            form = EditEventForm(user=request.user, data={"text": obj.event_text,
                                                          "begin_datetime": obj.begin_datetime,
                                                          "end_datetime": obj.end_datetime,
                                                          "owner_importance": obj.owner_importance,
                                                          "shares": shared_users,
                                                          "pk": request.GET["pk"]})
            return render(request,
                           "CalendarApp/editevent.html",
                           {"form": form, "pk": request.GET["pk"], "type": request.GET["type"]})
        share = CalAppModels.User_Event.objects.filter(user=request.user).filter(event=obj)
        if share:
            form = EditSharedEventForm(data={"importance":share.first().importance, "pk": request.GET["pk"]})
            return render(request,
                          "CalendarApp/editevent.html",
                          {"form": form, "pk": request.GET["pk"], "type": request.GET["type"], "noDelete": True})
    raise PermissionDenied

def Contacts(request):
    if request.user.is_authenticated:
        if request.method == "GET":
            return _render_contacts_form(request)
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
                    contactObj = CalAppModels.Contact(user1=request.user, user2=otherUser, state="invited")
                    contactObj.save()
                    return _render_contacts_form(request)
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
        # Delete the contact relation
        contactObj.delete()

        _unshare_all_between_contacts(request.user, otherUser)

        # Populate new list of contacts
        return _render_contacts_form(request)
    else:
        raise PermissionDenied


def AcceptContact(request):
    if request.user.is_authenticated:
        try:
            other_user = CalAppModels.User.objects.get(pk=request.POST["pk"])
            contactObject = CalAppModels.Contact.objects.get(user1=other_user, user2=request.user)
            contactObject.state = "accepted"
            contactObject.save()
            return _render_contacts_form(request)
        except:
            return bad_request(request, "Failed")
    raise PermissionDenied


def CalShareToggle(request):
    if request.user.is_authenticated:
        try:
            sharee = CalAppModels.User.objects.get(pk=request.POST['pk'])
        except:
            return bad_request(request, "Failed")
        try:
            cal_share = CalAppModels.Cal_Share.objects.get(sharer=request.user, sharee=sharee)
            cal_share.delete()
        except:
            contacts, _, _ = _get_all_contacts(request)
            if sharee in contacts:
                cal_share = CalAppModels.Cal_Share(sharer=request.user, sharee=sharee)
                cal_share.save()
            else:
                return bad_request(request, "Failed")
        return _render_contacts_form(request)
    else:
        raise PermissionDenied

def CalViewToggle(request):
    if request.user.is_authenticated:
        try:
            sharer = CalAppModels.User.objects.get(pk=request.POST['pk'])
        except:
            return bad_request(request, "Failed")
        try:
            cal_share = CalAppModels.Cal_Share.objects.get(sharer=sharer, sharee=request.user)
            if cal_share.status == "viewed":
                cal_share.status = "not viewed"
            else:
                cal_share.status = "viewed"
            cal_share.save()
        except:
            return bad_request(request, "Failed")
        return _render_contacts_form(request)
    else:
        raise PermissionDenied