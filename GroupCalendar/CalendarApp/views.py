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
import logging


class FailedToScheduleException(Exception):
    pass

class ScheduleTimedOutException(Exception):
    pass

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
                Schedule(request)
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
                        Schedule(request)
                        return HttpResponse(status="302", content="/")
                    else:
                        return render(request, "CalendarApp/EditEvent.html", {'form': form, "noDelete": 1})
                raise PermissionDenied
            form = EditEventForm(data=request.POST, user=request.user)
            if form.is_valid():
                CalAppEvent(form.cleaned_data, request.user).save(pk=obj.pk)
                Schedule(request)
                return HttpResponse(status="302", content="/")
            else:
                return render(request, "CalendarApp/EditEvent.html", {'form': form})
        except CalAppModels.Event.DoesNotExist:
            return bad_request(request, "Failed")

    def deleteEvent(request):
        try:
            obj = CalAppModels.Event.objects.get(pk=request.POST["pk"])
            if not obj.owner == request.user:
                raise PermissionDenied
            numSiblings = len(CalAppModels.Event.objects.filter(parent=obj.parent)) - 1
            if request.POST["all"] == 'true' or numSiblings == 0:
                obj = obj.parent
                obj.delete()
            else:
                obj.exception = True
                obj.scheduled = False
                obj.save()


            Schedule(request)
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
    """Various operations on tasks - get info, update info, create new, delete. Supports POST.
    Django does not support PUT or DELETE, at least easily, and so these are implemented with POST."""

    def addTask(request):
        # try:
        form = AddTaskForm(data=request.POST, user=request.user)
        if form.is_valid():
            CalAppTask(form.cleaned_data, request.user).save()
            Schedule(request)
            return HttpResponse(status="302", content="/")
        else:
            return render(request, "CalendarApp/AddTask.html", {'form': form})
        # except:
        #     return bad_request(request, "Failed")

    def editTask(request):
        # try:
        obj = CalAppModels.Task.objects.get(pk=request.POST["pk"])
        if request.POST["all"] == 'true':
            obj = obj.parent
        if not obj.owner == request.user:
            shares = CalAppModels.User_Task.objects.filter(user=request.user).filter(task=obj)
            if shares:
                form = EditSharedTaskForm(data=request.POST)
                if form.is_valid():
                    share = shares.first()
                    share.importance = request.POST["importance"]
                    share.save()
                    Schedule(request)
                    return HttpResponse(status="302", content="/")
                else:
                    return render(request, "CalendarApp/EditTask.html", {'form': form, "noDelete": 1})
            raise PermissionDenied
        form = EditTaskForm(data=request.POST, user=request.user)
        if form.is_valid():
            CalAppTask(form.cleaned_data, request.user).save(pk=obj.pk)
            Schedule(request)
            return HttpResponse(status="302", content="/")
        else:
            return render(request, "CalendarApp/EditTask.html", {'form': form})
        # except CalAppModels.Task.DoesNotExist:
        #     return bad_request(request, "Failed")

    def deleteTask(request):
        # try:

        obj = CalAppModels.Task.objects.get(pk=request.POST["pk"])
        if not obj.owner == request.user:
            raise PermissionDenied
        numSiblings = len(CalAppModels.Task.objects.filter(parent=obj.parent)) - 1
        if request.POST["all"] == 'true' or numSiblings == 0:
            obj = obj.parent
            obj.delete()
        else:
            obj.exception = True
            obj.scheduled = False
            obj.save()


        Schedule(request)
        return HttpResponse(status="302", content="/")
        # except:
        #     return bad_request(request, "Failed")

    if request.user.is_authenticated:
        if request.method == "POST":
            if request.POST["req"] == "put":
                return addTask(request)
            elif request.POST["req"] == "post":
                return editTask(request)
            elif request.POST["req"] == "delete":
                return deleteTask(request)

    raise PermissionDenied


def AddEvent(request):
    """Provides the Add Event form. Supports GET."""
    return render(request, "CalendarApp/AddEvent.html", {'form': AddEventForm(user=request.user)})


def AddTask(request):
    """Provides the Add Task form. Supports GET."""
    return render(request, "CalendarApp/AddTask.html", {'form': AddTaskForm(user=request.user)})

def _related_by_user(calItem1, calItem2):
    owner1 = calItem1.owner
    owner2 = calItem2.owner
    if owner1 == owner2:
        return True
    if type(calItem1) == CalAppModels.Task:
        shares = CalAppModels.User_Task.objects.filter(task=calItem1)
        usersShared1 = [share.user for share in shares]
    else:
        shares = CalAppModels.User_Event.objects.filter(task=calItem1)
        usersShared1 = [share.user for share in shares]

    if type(calItem2) == CalAppModels.Task:
        shares = CalAppModels.User_Task.objects.filter(task=calItem2)
        usersShared2 = [share.user for share in shares]
    else:
        shares = CalAppModels.User_Event.objects.filter(task=calItem2)
        usersShared2 = [share.user for share in shares]

    if owner1 in usersShared2 or owner2 in usersShared1:
        return True
    return False

def _conflicting(calItem1, calItem2):
    return _related_by_user(calItem1, calItem2) and (calItem1.begin_datetime > calItem2.begin_datetime and calItem1.begin_datetime < calItem2.end_datetime)\
            or (calItem2.begin_datetime > calItem1.begin_datetime and calItem2.begin_datetime < calItem1.end_datetime)\
            or (calItem1.begin_datetime == calItem2.begin_datetime)

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

def _get_constrainedness(calItem):
    if type(calItem) == CalAppModels.Task:
        numerator = (calItem.expected_minutes * 60) ** 1.1
        denominator = (calItem.due_date - calItem.available_date).total_seconds()
        return numerator / denominator
    elif type(calItem) == CalAppModels.Event:
        return (calItem.end_datetime - calItem.begin_datetime).total_seconds() ** 1.1
    else:
        raise Exception("Wrong data type! Expected task or event.")

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
        constrainedness = _get_constrainedness(event)
        cal_item_stats.append([event, averagePriority * constrainedness, maxPriority * constrainedness, False])

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
        constrainedness = _get_constrainedness(task)
        cal_item_stats.append([task, averagePriority * constrainedness, maxPriority * constrainedness, False])
    return cal_item_stats

needToReschedule = []
measure = 0

def _create_schedule(scheduled, unscheduled, tick, second_limit, possibilitiesBelowExhausted):
    global needToReschedule, measure
    rightNow = datetime.datetime.now()
    iAmExhausted = False
    if time.time() - tick > second_limit:
        raise ScheduleTimedOutException("Timed out!")
    repeatEverything = True
    disallowed_datetimes = set()
    interval = 480  # minutes
    while repeatEverything and len(unscheduled) > 0:
        repeatEverything = False
        item_to_schedule = unscheduled[-1]
        if type(item_to_schedule[0]) == CalAppModels.Event:
            iAmExhausted = True
            givenUp = False
            for item in scheduled:
                if _conflicting(item[0], item_to_schedule[0]):
                    if type(item[0]) == CalAppModels.Task and not possibilitiesBelowExhausted:
                        needToReschedule.append(item)
                        raise FailedToScheduleException("Can't schedule event")
                    else:
                        unscheduled.remove(item_to_schedule)
                        item_to_schedule[0].scheduled = False
                        givenUp = True
                        break
            if not givenUp:
                scheduled.append(item_to_schedule)
                unscheduled.remove(item_to_schedule)
        else:
            overdue = item_to_schedule[0].begin_datetime + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes) > item_to_schedule[0].due_date \
                      or make_aware(rightNow + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes)) > item_to_schedule[0].due_date
            item_to_schedule[0].begin_datetime = item_to_schedule[0].available_date
            item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime + datetime.timedelta(
                minutes=item_to_schedule[0].expected_minutes)
            if item_to_schedule[0].begin_datetime < make_aware(rightNow):
                item_to_schedule[0].begin_datetime = make_aware(rightNow)
                item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime + datetime.timedelta(
                    minutes=item_to_schedule[0].expected_minutes)
            success = False
            while (not success) and (interval >= max(15, item_to_schedule[0].expected_minutes // 2)):
                conflict = False
                for item in scheduled:
                    if _conflicting(item[0], item_to_schedule[0]):
                        item_to_schedule[0].begin_datetime = item[0].end_datetime
                        item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime + datetime.timedelta(
                            minutes=item_to_schedule[0].expected_minutes)
                        conflict = True
                        break
                if item_to_schedule[0].begin_datetime in disallowed_datetimes:
                    item_to_schedule[0].begin_datetime += datetime.timedelta(minutes=interval)
                    item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime + datetime.timedelta(
                        minutes=item_to_schedule[0].expected_minutes)
                    conflict = True
                if not conflict:
                    item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes)
                    scheduled.append(item_to_schedule)
                    unscheduled.remove(item_to_schedule)
                    success = True
                    break
                if overdue:
                    if item_to_schedule[0].begin_datetime + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes) \
                            > make_aware(rightNow + datetime.timedelta(days=1)):
                        item_to_schedule[0].begin_datetime = max(make_aware(rightNow), item_to_schedule[0].available_date)
                        item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime + datetime.timedelta(
                            minutes=item_to_schedule[0].expected_minutes)
                        interval /= 2
                else:
                    if item_to_schedule[0].begin_datetime + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes) > item_to_schedule[0].due_date:
                        item_to_schedule[0].begin_datetime = item_to_schedule[0].available_date
                        item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime + datetime.timedelta(
                            minutes=item_to_schedule[0].expected_minutes)
                        interval /= 2
            if not success:
                if possibilitiesBelowExhausted:
                    iAmExhausted = True
                    print("I got exhausted, as well as everyone below me!")
                    print("I am ", item_to_schedule[0].task_text, "due at", item_to_schedule[0].due_date)
                else:
                    raise FailedToScheduleException("Can't schedule task")

        try:
            _create_schedule(scheduled, unscheduled, tick, second_limit, iAmExhausted)
        except FailedToScheduleException as ex:
            if needToReschedule and not (item_to_schedule in needToReschedule):
                print("Skipped down")
                unscheduled.append(item_to_schedule)
                scheduled.remove(item_to_schedule)
                if possibilitiesBelowExhausted:
                    raise Exception("You shouldn't be seeing this!")
                raise FailedToScheduleException("Pass it on, there's something specific to reschedule.")
            if type(item_to_schedule[0]) == CalAppModels.Task and not iAmExhausted:
                # print("I can reschedule, I will.")
                unscheduled.append(item_to_schedule)
                scheduled.remove(item_to_schedule)
                disallowed_datetimes.add(item_to_schedule[0].begin_datetime)
                repeatEverything = True
            elif not possibilitiesBelowExhausted:
                # print("Either I was an event, or I could not be rescheduled.")
                if item_to_schedule in scheduled:
                    unscheduled.append(item_to_schedule)
                    scheduled.remove(item_to_schedule)
                raise FailedToScheduleException("Pass it on!")
            else:
                # print("You should never see this! You got an exception when rescheduling cannot happen!")
                # print("The exception was:", ex)
                exit(1)

def _get_all_related_scheduling_info(user):
    logger = logging.getLogger("mylogger")
    logger.info("Getting related scheduling info....")
    all_events = set(CalAppModels.Event.objects.filter(owner=user, parent__isnull=False, exception=False))
    all_tasks = set(CalAppModels.Task.objects.filter(owner=user, parent__isnull=False, exception=False))
    all_event_shares = CalAppModels.User_Event.objects.filter(event__in=all_events)
    all_task_shares = set(CalAppModels.User_Task.objects.filter(task__in=all_tasks))
    all_related_users = {share.user for share in all_event_shares}
    for share in all_task_shares:
        all_related_users.add(share.user)
    for event in all_events:
        all_related_users.add(event.owner)
    for task in all_tasks:
        all_related_users.add(task.owner)
    num_users = len(all_related_users)
    new_num_users = len(all_related_users) - 1
    while new_num_users != 0:
        logger.info("Have to loop...")
        num_users = len(all_related_users)
        for related_user in all_related_users:
            all_events = all_events.union(set(CalAppModels.Event.objects.filter(owner=related_user, parent__isnull=False, exception=False)))
            all_tasks = all_tasks.union(set(CalAppModels.Task.objects.filter(owner=related_user, parent__isnull=False, exception=False)))
        new_event_shares = CalAppModels.User_Event.objects.filter(event__in=all_events)
        all_event_shares = all_event_shares.union(new_event_shares)
        all_task_shares = all_task_shares.union(set(CalAppModels.User_Task.objects.filter(task__in=all_tasks)))
        for share in all_event_shares:
            all_related_users.add(share.user)
        for share in all_task_shares:
            all_related_users.add(share.user)
        for event in all_events:
            all_related_users.add(event.owner)
        for task in all_tasks:
            all_related_users.add(task.owner)
        new_num_users = len(all_related_users) - num_users
    for related_user in all_related_users:
        all_events = all_events.union(set(CalAppModels.Event.objects.filter(owner=related_user, parent__isnull=False, exception=False)))
        all_tasks = all_tasks.union(set(CalAppModels.Task.objects.filter(owner=related_user, parent__isnull=False, exception=False)))
    logger.info("Done!")
    return all_events, all_tasks, all_related_users

def _schedule_user_quick(user):
    logger = logging.getLogger("mylogger")
    tick = time.time()
    all_events, all_tasks, all_related_users = _get_all_related_scheduling_info(user)
    cal_item_stats = sorted(_get_cal_item_stats(all_events, all_tasks, all_related_users),
                            key=lambda a: a[1] + a[2] * 0.1)
    for cal_item in cal_item_stats:
        cal_item[0].scheduled = False
        cal_item[0].save()
    #schedule events and tasks
    to_schedule = []
    while len(cal_item_stats) > 0:
        if time.time() - tick > 30:
            break
        for cal_item in to_schedule:
            cal_item[0].scheduled = False
        next_item = cal_item_stats.pop(-1)
        if type(next_item[0]) == CalAppModels.Event:
            while next_item[0].begin_datetime.date() < make_aware(datetime.datetime.now()).date():
                next_item[0].scheduled = True
                next_item[0].save()
                next_item = cal_item_stats.pop(-1)
        to_schedule = [next_item] + to_schedule
        unscheduled = copy.copy(to_schedule)
        scheduled = []
        last_successful = []
        try:
            tick2 = time.time()
            _create_schedule(scheduled, unscheduled, tick, 30, True)
            last_successful = (copy.copy(scheduled), copy.copy(unscheduled))
            logger.info("Successfully scheduled" + str(len(scheduled)) + "items")
            if (time.time() - tick2 > 0.01) or (time.time() - tick > 20) or len(cal_item_stats) == 0 or len(scheduled) % 10 == 0:
                for item in unscheduled:
                    item[0].scheduled = False
                    item[0].save()
                for item in scheduled:
                    item[0].scheduled = True
                    item[0].save()
        except Exception as e:
            # if last_successful:
            #     for item in last_successful[1]:
            #         item[0].scheduled = False
            #         item[0].save()
            #     for item in last_successful[0]:
            #         item[0].scheduled = True
            #         item[0].save()
            logger.info(e)
            return

def _try_to_schedule_before(item_to_schedule, scheduled, time_to_schedule_before):
    interval = 480
    right_now = datetime.datetime.now()
    success = False
    to_remove = []
    item_to_schedule[0].begin_datetime = max(make_aware(right_now), item_to_schedule[0].available_date)
    item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes)
    while interval > 1 and not success:
        conflict = False
        for item in scheduled:
            if _conflicting(item[0], item_to_schedule[0]):
                conflict = True
                if item[1]+item[2]*0.1 < item_to_schedule[1]+item_to_schedule[2]*0.1:
                #if (type(item[0]) == CalAppModels.Event and item[1]+item[2]*0.1 < item_to_schedule[1]+item_to_schedule[2]*0.1) or (type(item[0]) == CalAppModels.Task):
                    if item not in to_remove:
                        to_remove.append(item)
        if conflict:
            item_to_schedule[0].begin_datetime += datetime.timedelta(minutes=interval)
            item_to_schedule[0].end_datetime += datetime.timedelta(minutes=interval)
        else:
            item_to_schedule[0].scheduled = True
            scheduled.append(item_to_schedule)
            success = True
            to_remove = []
        if item_to_schedule[0].end_datetime > time_to_schedule_before:
            interval //= 2
            item_to_schedule[0].begin_datetime = max(make_aware(right_now), item_to_schedule[0].available_date)
            item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes)
        else:
            pass

    return success, to_remove

def _add_task_to_schedule(item_to_schedule, scheduled):
    logger = logging.getLogger("mylogger")
    right_now = datetime.datetime.now()
    logger.info("attempting to add the item before its due date, first try")
    success, to_remove = _try_to_schedule_before(item_to_schedule, scheduled, item_to_schedule[0].due_date)
    if to_remove and not success:
        for item in to_remove:
            item[0].scheduled = False
            scheduled.remove(item)
        logger.info("Fail, removed items. Second try.")
        success, _ = _try_to_schedule_before(item_to_schedule, scheduled, item_to_schedule[0].due_date)
        if not success:
            logger.info("Failed. Replaced items.")
            for item in to_remove:
                item[0].scheduled = True
                scheduled.append(item)
            to_remove = []
            scheduled = sorted(scheduled, key=lambda a: a[1] + a[2] * 0.1)
        else:
            logger.info("Succeeded on second try")
            return success, to_remove
    hourIncrement = 24
    while (hourIncrement <= 72) and (not success):
        if item_to_schedule[0].due_date < make_aware(right_now + datetime.timedelta(hours=hourIncrement)):
            success, to_remove = _try_to_schedule_before(item_to_schedule, scheduled, make_aware(
                right_now + datetime.timedelta(hours=hourIncrement)))
            if to_remove and not success:
                for item in to_remove:
                    item[0].scheduled = False
                    scheduled.remove(item)
                success, _ = _try_to_schedule_before(item_to_schedule, scheduled,
                                                     make_aware(right_now + datetime.timedelta(hours=hourIncrement)))
                if not success:
                    for item in to_remove:
                        item[0].scheduled = True
                        scheduled.append(item)
                    to_remove = []
                    scheduled = sorted(scheduled, key=lambda a: a[1] + a[2] * 0.1)
                else:
                    return success, to_remove
        hourIncrement += 24
    return success, []

def _add_event_to_schedule(item_to_schedule, scheduled):
    logger = logging.getLogger("mylogger")
    to_remove = []
    removed_items = []
    for item in scheduled:
        conflict = _conflicting(item[0], item_to_schedule[0])
        if conflict:
            if type(item[0]) == CalAppModels.Task:
                logger.info("Conflict found with:", item[0].task_text)
                logger.info("Trying to reschedule the other")
                to_remove.append(item)
            else:
                logger.info("Conflict found with:", item[0].event_text)
                if item_to_schedule[1] + item_to_schedule[2] * 0.1 > item[1] + item[2] * 0.1:
                    logger.info("Trying to reschedule the other")
                    to_remove.append(item)
                else:
                    logger.info("Not going to bother trying to reschedule the other")
                    return False, []

    item_to_schedule[0].scheduled = True
    scheduled.append(item_to_schedule)
    for item in to_remove:
        item[0].scheduled = False
        scheduled.remove(item)

    overall_success = True

    logger.info("Length of to_remove:" + str(len(to_remove)))

    for i in range(len(to_remove)-1, -1, -1):  # backwards to ensure removing items works
        item = to_remove[i]
        logger.info("Trying to reschedule an item...")
        if type(item[0]) == CalAppModels.Task:
            logger.info("The item is a task")
            success, _ = _try_to_schedule_before(item, scheduled, item[0].due_date)
            if not success:
                logger.info("One of them failed to reschedule once I was put in")
                if item_to_schedule[1] + item_to_schedule[2] * 0.1 > item[1] + item[2] * 0.1:
                    logger.info("But it's OK because I'm more important")
                else:
                    logger.info("and I'm less important, so I'm unscheduling myself")
                    overall_success = False
                    item_to_schedule[0].scheduled = False
                    scheduled.remove(item_to_schedule)
                    break
            else:
                logger.info("Succeeded in rescheduling a removed item once I was put in")
                logger.info("I am scheduled for" + str(item_to_schedule[0].begin_datetime))
                logger.info("Other is scheduled for" + str(item[0].begin_datetime))
                to_remove.remove(item)
                item[0].save()
    logger.info("got here...")
    for item in to_remove:
        logger.info("There are still" + str(len(to_remove)) + "items in to_remove")
        if type(item[0]) == CalAppModels.Task:
            logger.info("This one is a task")
            success, _ = _try_to_schedule_before(item, scheduled, item[0].due_date)
        else:
            logger.info("This one is an event")
            success, removed = _add_event_to_schedule(item, scheduled)
            removed_items.append += removed
        if not success:
            logger.info("Unsuccessful in rescheduling this item")
            removed_items.append(item)
        else:
            item[0].save()
    return overall_success, removed_items



def _schedule_user_quick_2(user):
    logger = logging.getLogger("mylogger")
    tick = time.time()
    right_now = datetime.datetime.now()
    all_events, all_tasks, all_related_users = _get_all_related_scheduling_info(user)
    cal_item_stats = sorted(_get_cal_item_stats(all_events, all_tasks, all_related_users),
                            key=lambda a: a[1] + a[2] * 0.1)
    scheduled = []
    unscheduled = []
    for item in cal_item_stats:
        if type(item[0]) == CalAppModels.Task and \
                (item[0].begin_datetime < make_aware(right_now) or item[0].end_datetime > item[0].due_date):
            item[0].scheduled = False
            item[0].save()
        if item[0].scheduled:
            scheduled.append(item)
        else:
            unscheduled.append(item)

    while (time.time() - tick < 30) and len(unscheduled) > 0:
        item_to_schedule = unscheduled.pop(-1)
        if type(item_to_schedule[0]) == CalAppModels.Task:
            logger.info("Attempting to add" + item_to_schedule[0].task_text)
            success, removed_items = _add_task_to_schedule(item_to_schedule, scheduled)
        else:
            logger.info("Attempting to add", item_to_schedule[0].event_text)
            success, removed_items = _add_event_to_schedule(item_to_schedule, scheduled)
        if removed_items:
            logger.info("Removed" +  str(removed_items) + "during the attempt")
            for item in removed_items:
                unscheduled.append(item)
                item[0].scheduled = False
                item[0].save()
                unscheduled = sorted(unscheduled, key=lambda a: a[1] + a[2] * 0.1)
        if success:
            logger.info("Succeeded")
            scheduled.append(item_to_schedule)

        else:
            logger.info("Failed")
        item_to_schedule[0].save()


def Schedule(request):
    """Causes the schedule to run. Supports POST."""
    if not _schedule_main_loop_is_running:
        # asyncio.run(_scheduling_main_loop())
        pass
    if request.user.is_authenticated:
        _schedule_user_quick_2(request.user)
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
        Schedule(request)
        eventsOwned = CalAppModels.Event.objects.filter(owner=request.user, exception=False, scheduled=True).exclude(parent__isnull=True)
        tasksOwned = CalAppModels.Task.objects.filter(owner=request.user, exception=False, scheduled=True).exclude(parent__isnull=True)
        event_shares = CalAppModels.User_Event.objects.filter(user=request.user)
        task_shares = CalAppModels.User_Task.objects.filter(user=request.user)
        eventsSharedSet = {share.event for share in event_shares}
        tasksSharedSet = {share.task for share in task_shares}
        eventPKs = {event.pk for event in eventsSharedSet}
        taskPKs = {task.pk for task in tasksSharedSet}
        eventsShared = CalAppModels.Event.objects.filter(pk__in=eventPKs, exception=False, scheduled=True).exclude(parent__isnull=True)
        tasksShared = CalAppModels.Task.objects.filter(pk__in=taskPKs, exception=False, scheduled=True).exclude(parent__isnull=True)
        calendars_shared_with_me = CalAppModels.Cal_Share.objects.filter(sharee=request.user, status="viewed")
        users_sharing_calendars_with_me = {calendar.sharer for calendar in calendars_shared_with_me}
        events_in_calendars_shared_with_me = set()
        tasks_in_calendars_shared_with_me = set()
        for user in users_sharing_calendars_with_me:
            events = CalAppModels.Event.objects.filter(owner=user, exception=False, scheduled=True).exclude(parent__isnull=True)
            tasks = CalAppModels.Task.objects.filter(owner=user, exception=False, scheduled=True).exclude(parent__isnull=True)
            if events_in_calendars_shared_with_me:
                events_in_calendars_shared_with_me = events_in_calendars_shared_with_me.union(events)
            else:
                events_in_calendars_shared_with_me = copy.copy(events)
            if tasks_in_calendars_shared_with_me:
                tasks_in_calendars_shared_with_me = tasks_in_calendars_shared_with_me.union(tasks)
            else:
                tasks_in_calendars_shared_with_me = copy.copy(tasks)
        events_in_calendars_shared_with_me = events_in_calendars_shared_with_me.difference(eventsShared)
        tasks_in_calendars_shared_with_me = tasks_in_calendars_shared_with_me.difference(tasksShared)
    else:
        eventsOwned = set()
        eventsShared = set()
        events_in_calendars_shared_with_me = set()
        tasksOwned = set()
        tasksShared = set()
        tasks_in_calendars_shared_with_me = set()

    repeatForm = RepetitionForm()
    return render(request, "CalendarApp/index.html", {"eventsOwned": eventsOwned,
                                                      "eventsShared": eventsShared,
                                                      "eventsInViewedCalendars": events_in_calendars_shared_with_me,
                                                      "tasksOwned": tasksOwned,
                                                      "tasksShared": tasksShared,
                                                      "tasksInViewedCalendars": tasks_in_calendars_shared_with_me,
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
        numSiblings = len(CalAppModels.Task.objects.filter(parent=obj.parent)) - 1
    except:
        return bad_request(request, "Failed")
    if request.user.is_authenticated:
        if obj.owner == request.user:
            form = EditTaskForm(user=request.user, data={"text": obj.task_text,
                                                          "due_datetime": obj.due_date,
                                                          "available_datetime": obj.available_date,
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
                           {"form": form,
                            "pk": request.GET["pk"],
                            "type": request.GET["type"],
                            "hasSiblings": numSiblings > 0})
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
        Schedule(request)
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
            Schedule(request)
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