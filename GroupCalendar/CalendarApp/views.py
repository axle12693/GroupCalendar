from django.shortcuts import render
from django.http import HttpResponse
from .forms import UserRegisterForm, AddEventForm, AddTaskForm, EditEventForm, EditTaskForm, AddContactForm, EditSharedEventForm, EditSharedTaskForm, RepetitionForm
from django.core.exceptions import PermissionDenied
from django.views.defaults import bad_request
from .CalendarItem import Task as CalAppTask, Event as CalAppEvent
from . import models as CalAppModels
import copy
from math import log2
import datetime
from django.conf import settings
import asyncio
import time
from django.utils.timezone import make_aware

# Each function will handle, where appropriate, more than one HTTP method

_schedule_main_loop_is_running = False
_schedule_queued_users_is_running = False
_queue_all_users_is_running = False

# async def _scheduling_main_loop():
#     while 1:
#         # Start another async function to schedule queued users. This should not loop forever. This should only
#         #   start if it is not already running.
#         if not _schedule_queued_users_is_running:
#             asyncio.run(_schedule_queued_users())
#         # Every 3 hours, start another async function to queue all users.
#
#         await asyncio.sleep(60)
#
# async def _schedule_queued_users():
#     while 1:
#
# async def _queue_all_users():
#     pass

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


def Event(request):
    """Various operations on events - get info, update info, create new, delete. Supports POST.
    Django does not support PUT or DELETE, at least easily, and so these are implemented with POST."""

    def addEvent(request):
        try:
            form = AddEventForm(data=request.POST, user=request.user)
            if form.is_valid():
                CalAppEvent(form.cleaned_data, request.user).save()
                return HttpResponse(status="302", content="/")
            else:
                return render(request, "CalendarApp/AddEvent.html", {'form': form})
        except:
            return bad_request(request, "Failed")

    def editEvent(request):
        try:
            obj = CalAppModels.Event.objects.get(pk=request.POST["pk"])
            if request.POST["all"] == 'true':
                obj = obj.parent
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
                        return render(request, "CalendarApp/EditEvent.html", {'form': form, "noDelete": 1})
                raise PermissionDenied
            form = EditEventForm(data=request.POST, user=request.user)
            if form.is_valid():
                CalAppEvent(form.cleaned_data, request.user).save(pk=obj.pk)
                return HttpResponse(status="302", content="/")
            else:
                return render(request, "CalendarApp/EditEvent.html", {'form': form})
        except CalAppModels.Event.DoesNotExist:
            return bad_request(request, "Failed")

    def deleteEvent(request):
        try:
            obj = CalAppModels.Event.objects.get(pk=request.POST["pk"])
            numSiblings = len(CalAppModels.Event.objects.filter(parent=obj.parent)) - 1
            if request.POST["all"] == 'true' or numSiblings == 0:
                obj = obj.parent
            if not obj.owner == request.user:
                raise PermissionDenied
            obj.delete()
            return HttpResponse(status="302", content="/")
        except:
            return bad_request(request, "Failed")

    if request.user.is_authenticated:
        if request.method == "POST":
            if request.POST["req"] == "put":
                return addEvent(request)
            elif request.POST["req"] == "post":
                return editEvent(request)
            elif request.POST["req"] == "delete":
                return deleteEvent(request)

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
                        return HttpResponse(status="302", content="/")
                    else:
                        return render(request, "CalendarApp/AddTask.html", {'form': form})
                except:
                    return bad_request(request, "Failed")
            elif request.POST["req"] == "post":
                try:
                    obj = CalAppModels.Task.objects.get(pk=request.POST["pk"])
                    if not obj.owner == request.user:
                        shares = CalAppModels.User_Task.objects.filter(user=request.user).filter(event=obj)
                        if shares:
                            form = EditSharedTaskForm(data=request.POST)
                            if form.is_valid():
                                share = shares.first()
                                share.importance = request.POST["importance"]
                                share.save()
                                return HttpResponse(status="302", content="/")
                            else:
                                return render(request, "CalendarApp/EditTask.html", {'form': form, "noDelete": 1})
                        raise PermissionDenied
                    form = EditTaskForm(data=request.POST, user=request.user)
                    if form.is_valid():
                        pk = request.POST["pk"]
                        CalAppTask(form.cleaned_data, request.user).save(pk=pk)
                        return HttpResponse(status="302", content="/")
                    else:
                        return render(request, "CalendarApp/EditTask.html", {'form': form})
                except CalAppModels.Task.DoesNotExist:
                    return bad_request(request, "Failed")
            elif request.POST["req"] == "delete":
                try:
                    obj = CalAppModels.Task.objects.get(pk=request.POST["pk"])
                    if not obj.owner == request.user:
                        raise PermissionDenied
                    obj.delete()
                    return HttpResponse(status="302", content="/")
                except:
                    return bad_request(request, "Failed")
        elif request.method == "GET":
            pass

    raise PermissionDenied


def AddEvent(request):
    """Provides the Add Event form. Supports GET."""
    return render(request, "CalendarApp/AddEvent.html", {'form': AddEventForm(user=request.user)})


def AddTask(request):
    """Provides the Add Task form. Supports GET."""
    return render(request, "CalendarApp/AddTask.html", {'form': AddTaskForm(user=request.user)})

def _conflicting(calItem1, calItem2):
    return (calItem1.begin_datetime > calItem2.begin_datetime and calItem1.begin_datetime < calItem2.end_datetime)\
            or (calItem2.begin_datetime > calItem1.begin_datetime and calItem2.begin_datetime < calItem1.end_datetime)

def _get_priority(calItem, user):
    due_date = calItem.due_date if type(calItem) == CalAppModels.Task else calItem.begin_datetime
    if calItem.owner == user:
        importance = calItem.owner_importance
    else:
        try:
            if type(calItem) == CalAppModels.Task:
                importance = CalAppModels.User_Task.objects.get(user=user).importance
            else:
                importance = CalAppModels.User_Event.objects.get(user=user).importance
        except:
            importance = 0

    return (importance + 0.01) ** 1.1 + ((make_aware(datetime.datetime.now()).toordinal() - due_date.toordinal()) + 0.01)

def _get_cal_item_stats(all_events, all_tasks, all_related_users):
    cal_item_stats = []
    for event in all_events:
        owner_priority = _get_priority(event, event.owner)
        totalPriority = owner_priority
        maxPriority = owner_priority
        numPriorities = 1
        for related_user in all_related_users:
            priority = _get_priority(event, related_user)
            totalPriority += priority
            maxPriority = max(maxPriority, priority)
            numPriorities += 1
        averagePriority = totalPriority / numPriorities
        cal_item_stats.append((event, averagePriority, maxPriority))

    for task in all_tasks:
        owner_priority = _get_priority(task, task.owner)
        totalPriority = owner_priority
        maxPriority = owner_priority
        numPriorities = 1
        for related_user in all_related_users:
            priority = _get_priority(task, related_user)
            totalPriority += priority
            maxPriority = max(maxPriority, priority)
            numPriorities += 1
        averagePriority = totalPriority / numPriorities
        cal_item_stats.append((task, averagePriority, maxPriority))
    return cal_item_stats

def _create_schedule(scheduled, unscheduled, tick, second_limit):
    print("It has taken", time.time() - tick, "seconds to shcedule", len(scheduled), "items")
    if time.time() - tick > second_limit:
        raise Exception("Out of time!")
    repeatEverything = True
    disallowed_datetimes = set()
    interval = 480  # minutes
    while repeatEverything and len(unscheduled) > 0:
        repeatEverything = False
        item_to_schedule = unscheduled[-1]
        if type(item_to_schedule[0]) == CalAppModels.Event:
            givenUp = False
            for item in scheduled:
                if _conflicting(item[0], item_to_schedule[0]):
                    if type(item[0]) == CalAppModels.Task:
                        raise Exception("Can't schedule event")
                    else:
                        unscheduled.remove(item_to_schedule)
                        item_to_schedule[0].scheduled = False
                        item_to_schedule[0].save()
                        givenUp = True
                        break
            if not givenUp:
                scheduled.append(item_to_schedule)
                unscheduled.remove(item_to_schedule)
        else:
            overdue = item_to_schedule[0].begin_datetime + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes) > item_to_schedule[0].due_date \
                      or datetime.datetime.now() + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes) > item_to_schedule[0].due_date
            if item_to_schedule[0].begin_datetime < item_to_schedule[0].available_date:
                item_to_schedule[0].begin_datetime = item_to_schedule[0].available_date
            if item_to_schedule[0].begin_datetime < datetime.datetime.now() + datetime.timedelta(minutes=15):
                item_to_schedule[0].begin_datetime = datetime.datetime.now() + datetime.timedelta(minutes=15)

            success = False
            while (not success) and (interval <= 15):
                conflict = False
                for item in scheduled:
                    if _conflicting(item[0], item_to_schedule[0]) or item_to_schedule[0].begin_datetime in disallowed_datetimes:
                        item_to_schedule[0].begin_datetime += datetime.timedelta(minutes=interval)
                        conflict = True
                        break
                if not conflict:
                    scheduled.append(item_to_schedule)
                    unscheduled.remove(item_to_schedule)
                    success = True
                    break
                if overdue:
                    if item_to_schedule[0].begin_datetime + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes) \
                            > datetime.datetime.now() + datetime.timedelta(days=1):
                        item_to_schedule[0].begin_datetime = item_to_schedule[0].available_date
                        interval /= 2
                else:
                    if item_to_schedule[0].begin_datetime + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes) > item_to_schedule[0].due_date:
                        item_to_schedule[0].begin_datetime = item_to_schedule[0].available_date
                        interval /= 2
            if not success:
                raise Exception("Can't schedule task")

        try:
            _create_schedule(scheduled, unscheduled, tick, second_limit)
        except:
            if type(item_to_schedule[0]) == CalAppModels.Task:
                unscheduled.append(item_to_schedule)
                scheduled.remove(item_to_schedule)
                disallowed_datetimes.add(item_to_schedule[0].begin_datetime)
                repeatEverything = True
            else:
                raise Exception("Pass it on!")

def _schedule_user_quick(user):
    tick = time.time()
    all_events = CalAppModels.Event.objects.filter(owner=user)
    all_tasks = CalAppModels.Task.objects.filter(owner=user)
    all_event_shares = CalAppModels.User_Event.objects.filter(event__in=all_events)
    all_task_shares = CalAppModels.User_Task.objects.filter(task__in=all_tasks)
    all_related_user_pks = []
    for share in all_event_shares:
        all_related_user_pks.append(share.user.pk)
    for share in all_task_shares:
        all_related_user_pks.append(share.user.pk)
    all_related_users = CalAppModels.User.objects.filter(pk__in=all_related_user_pks)
    num_users = len(all_related_users)
    new_num_users = 0
    while num_users != new_num_users:
        num_users = new_num_users
        for related_user in all_related_users:
            all_events = all_events.union(CalAppModels.Event.objects.filter(owner=related_user))
            all_tasks = all_tasks.union(CalAppModels.Task.objects.filter(owner=related_user))
        all_event_shares = all_event_shares.union(CalAppModels.User_Event.objects.filter(event__in=all_events))
        all_task_shares = all_task_shares.union(CalAppModels.User_Task.objects.filter(task__in=all_tasks))
        all_related_user_pks = []
        for share in all_event_shares:
            all_related_user_pks.append(share.user.pk)
        for share in all_task_shares:
            all_related_user_pks.append(share.user.pk)
        for event in all_events:
            all_related_user_pks.append(event.owner.pk)
        for task in all_tasks:
            all_related_user_pks.append(task.owner.pk)
        all_related_users = CalAppModels.User.objects.filter(pk__in=all_related_user_pks)
        new_num_users = len(all_related_users)
    for related_user in all_related_users:
        all_events = all_events.union(CalAppModels.Event.objects.filter(owner=related_user))
        all_tasks = all_tasks.union(CalAppModels.Task.objects.filter(owner=related_user))
    cal_item_stats = sorted(_get_cal_item_stats(all_events, all_tasks, all_related_users),
                            key=lambda a: a[1] + a[2] * 0.1)
    for cal_item in cal_item_stats:
        cal_item[0].scheduled = False
        cal_item[0].save()
    #schedule events and tasks
    to_schedule = []
    print("It took", time.time() - tick, "seconds to get to the point where scheduling can start")
    while len(cal_item_stats) > 0:
        if time.time() - tick > 30:
            break
        for cal_item in to_schedule:
            cal_item[0].scheduled = False
        to_schedule = [cal_item_stats.pop(-1)] + to_schedule
        unscheduled = copy.copy(to_schedule)
        scheduled = []
        try:
            tick2 = time.time()
            _create_schedule(scheduled, unscheduled, tick, 30)
            if ((time.time() - tick2 > 0.1) and (time.time() - tick > 20)) or (time.time() - tick > 27):
                for item in unscheduled:
                    item[0].scheduled = False
                    item[0].save()
                for item in scheduled:
                    item[0].scheduled = True
                    item[0].save()
        except:
            return




def Schedule(request):
    """Causes the schedule to run. Supports POST."""
    if not _schedule_main_loop_is_running:
        # asyncio.run(_scheduling_main_loop())
        pass
    if request.user.is_authenticated:
        _schedule_user_quick(request.user)
        return HttpResponse("Scheduled")
    raise PermissionDenied




def parseWeeklyDays(num):
    n = 8
    ls = []
    while n < num:
        n *= 2
    while n >= 1:
        if num % n != num:
            ls.append(int(n))
            num = num % n
        n /= 2
    return ls


def Index(request):
    """The index.html page that everyone expects. Supports GET."""
    if request.user.is_authenticated:
        eventsOwned = CalAppModels.Event.objects.filter(owner=request.user, exception=False, scheduled=True).exclude(parent__isnull=True)
        shares = CalAppModels.User_Event.objects.filter(user=request.user)
        eventsSharedSet = {share.event for share in shares}
        eventPKs = {event.pk for event in eventsSharedSet}
        eventsShared = CalAppModels.Event.objects.filter(pk__in=eventPKs, exception=False, scheduled=True).exclude(parent__isnull=True)
        calendars_shared_with_me = CalAppModels.Cal_Share.objects.filter(sharee=request.user, status="viewed")
        users_sharing_calendars_with_me = {calendar.sharer for calendar in calendars_shared_with_me}
        events_in_calendars_shared_with_me = set()
        for user in users_sharing_calendars_with_me:
            events = CalAppModels.Event.objects.filter(owner=user, exception=False, scheduled=True).exclude(parent__isnull=True)
            if events_in_calendars_shared_with_me:
                events_in_calendars_shared_with_me = events_in_calendars_shared_with_me.union(events)
            else:
                events_in_calendars_shared_with_me = copy.copy(events)

        events_in_calendars_shared_with_me = events_in_calendars_shared_with_me.difference(eventsShared)
    else:
        eventsOwned = set()
        eventsShared =set()
        events_in_calendars_shared_with_me = set()

    repeatForm = RepetitionForm()
    return render(request, "CalendarApp/index.html", {"eventsOwned": eventsOwned,
                                                      "eventsShared": eventsShared,
                                                      "eventsInViewedCalendars": events_in_calendars_shared_with_me,
                                                      "repeatForm": repeatForm})


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
    # try:
    obj = CalAppModels.Event.objects.get(pk=request.GET["pk"])
    shares = CalAppModels.User_Event.objects.filter(event=obj)
    shared_users = {share.user for share in shares}
    numSiblings = len(CalAppModels.Event.objects.filter(parent=obj.parent)) - 1
    # except:
    #     return bad_request(request, "Failed")
    if request.user.is_authenticated:
        if obj.owner == request.user:
            form = EditEventForm(user=request.user, data={"text": obj.event_text,
                                                          "begin_datetime": obj.begin_datetime,
                                                          "end_datetime": obj.end_datetime,
                                                          "owner_importance": obj.owner_importance,
                                                          "shares": shared_users,
                                                          "pk": request.GET["pk"],
                                                          "repetition_type": obj.repetition_type,
                                                          "repetition_number": obj.repetition_number,
                                                          "from_date": obj.from_date,
                                                          "until_date": obj.until_date})
            return render(request,
                           "CalendarApp/editevent.html",
                           {"form": form,
                            "pk": request.GET["pk"],
                            "type": request.GET["type"],
                            "hasSiblings": numSiblings > 0})
        share = CalAppModels.User_Event.objects.filter(user=request.user).filter(event=obj)
        if share:
            form = EditSharedEventForm(data={"importance":share.first().importance, "pk": request.GET["pk"]})
            return render(request,
                          "CalendarApp/editevent.html",
                          {"form": form, "pk": request.GET["pk"], "type": request.GET["type"], "noDelete": True})
    raise PermissionDenied

def EditTask(request):
    try:
        obj = CalAppModels.Task.objects.get(pk=request.GET["pk"])
        shares = CalAppModels.User_Task.objects.filter(task=obj)
        shared_users = {share.user for share in shares}
    except:
        return bad_request(request, "Failed")
    if request.user.is_authenticated:
        if obj.owner == request.user:
            form = EditTaskForm(user=request.user, data={"text": obj.event_text,
                                                          "due_datetime": obj.due_datetime,
                                                          "available_datetime": obj.available_datetime,
                                                          "owner_importance": obj.owner_importance,
                                                          "shares": shared_users,
                                                          "pk": request.GET["pk"],
                                                          "repetition_type": obj.repetition_type,
                                                          "repetition_number": obj.repetition_number,
                                                          "expected_minutes": obj.expected_minutes,
                                                          "from_date": obj.from_date,
                                                          "until_date": obj.until_date})
            return render(request,
                           "CalendarApp/edittask.html",
                           {"form": form, "pk": request.GET["pk"], "type": request.GET["type"]})
        share = CalAppModels.User_Task.objects.filter(user=request.user).filter(task=obj)
        if share:
            form = EditSharedTaskForm(data={"importance":share.first().importance, "pk": request.GET["pk"]})
            return render(request,
                          "CalendarApp/edittask.html",
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