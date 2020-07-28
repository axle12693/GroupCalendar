from django.shortcuts import render
from django.http import HttpResponse
from .forms import *
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.views.defaults import bad_request
from .CalendarItem import Task as CalAppTask, Event as CalAppEvent
from . import models as CalAppModels
import copy
import datetime
import time
from django.utils.timezone import make_aware
import logging
import threading
import random


class DBScheduleLock:
    lock = threading.Lock()

    @staticmethod
    def general_wait_for_unblock(user):
        DBScheduleLock.lock.acquire()
        try:
            obj = CalAppModels.User_Schedule_Lock.objects.get(user=user)
        except ObjectDoesNotExist:
            obj = CalAppModels.User_Schedule_Lock(user=user, block_all=0, num_waiting=0)
        obj.num_waiting += 1
        obj.save()
        DBScheduleLock.lock.release()
        while 1:
            DBScheduleLock.lock.acquire()
            obj = CalAppModels.User_Schedule_Lock.objects.get(user=user)
            if obj.block_all > 0:
                DBScheduleLock.lock.release()
                time.sleep(random.uniform(0.05, 0.5))
            else:
                obj.num_waiting -= 1
                obj.block_all += 1
                obj.save()
                DBScheduleLock.lock.release()
                break

    @staticmethod
    def dec_block(user):
        DBScheduleLock.lock.acquire()
        obj = CalAppModels.User_Schedule_Lock.objects.get(user=user)
        obj.block_all -= 1
        obj.save()
        DBScheduleLock.lock.release()


class FailedToScheduleException(Exception):
    pass


class ScheduleTimedOutException(Exception):
    pass


# Each function will handle, where appropriate, more than one HTTP method


_schedule_main_loop_is_running = False
_schedule_queued_users_is_running = False
_queue_all_users_is_running = False
_user_queue = []


def _scheduling_main_loop():
    global _schedule_main_loop_is_running, _schedule_queued_users_is_running, _queue_all_users_is_running
    while 1:
        if not _schedule_queued_users_is_running:
            thread1 = threading.Thread(target=_schedule_queued_users)
            thread1.start()
            _schedule_queued_users_is_running = True
        thread2 = threading.Thread(target=_queue_all_users)
        thread2.start()
        time.sleep(10800)


def _schedule_queued_users():
    global _user_queue
    logger = logging.getLogger("mylogger")
    while 1:
        if len(_user_queue) == 0:
            time.sleep(1)
            continue
        user = _user_queue[0]
        all_events, all_tasks, all_related_users = _get_all_related_scheduling_info(user)
        while 1:
            fail = False
            DBScheduleLock.lock.acquire()
            for r_user in all_related_users:
                try:
                    obj = CalAppModels.User_Schedule_Lock.objects.get(user=r_user)
                except ObjectDoesNotExist:
                    obj = CalAppModels.User_Schedule_Lock(user=r_user, block_all=0, num_waiting=0)
                    obj.save()
                if obj.block_all != 0:
                    fail = True
                    break
            if fail:
                DBScheduleLock.lock.release()
                time.sleep(random.uniform(0.05, 0.5))
            else:
                for r_user in all_related_users:
                    obj = CalAppModels.User_Schedule_Lock.objects.get(user=r_user)
                    obj.block_all += 1
                    obj.save()
                DBScheduleLock.lock.release()
                break

        _schedule_user_slow(user)

        DBScheduleLock.lock.acquire()
        for r_user in all_related_users:
            obj = CalAppModels.User_Schedule_Lock.objects.get(user=r_user)
            obj.block_all -= 1
            obj.save()
        DBScheduleLock.lock.release()


def _queue_all_users():
    global _user_queue
    users = CalAppModels.User.objects.all()
    for user in users:
        try:
            schedule_info = CalAppModels.User_Schedule_Info.objects.get(user=user)
        except ObjectDoesNotExist:
            schedule_info = None
        if user in _user_queue:
            continue
        if schedule_info \
                and make_aware(datetime.datetime.now()) - datetime.timedelta(hours=2) \
                < schedule_info.last_slow_schedule:
            continue
        _user_queue.append(user)


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
                DBScheduleLock.dec_block(request.user)
                Schedule(request)
                return HttpResponse(status="302", content="/")
            else:
                DBScheduleLock.dec_block(request.user)
                return render(request, "CalendarApp/AddEvent.html", {'form': form})
        except:
            DBScheduleLock.dec_block(request.user)
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
                        DBScheduleLock.dec_block(request.user)
                        Schedule(request)
                        return HttpResponse(status="302", content="/")
                    else:
                        DBScheduleLock.dec_block(request.user)
                        return render(request, "CalendarApp/EditEvent.html", {'form': form, "noDelete": 1})
                raise PermissionDenied
            form = EditEventForm(data=request.POST, user=request.user)
            if form.is_valid():
                CalAppEvent(form.cleaned_data, request.user).save(pk=obj.pk)
                DBScheduleLock.dec_block(request.user)
                Schedule(request)
                return HttpResponse(status="302", content="/")
            else:
                DBScheduleLock.dec_block(request.user)
                return render(request, "CalendarApp/EditEvent.html", {'form': form})
        except ObjectDoesNotExist:
            DBScheduleLock.dec_block(request.user)
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
            DBScheduleLock.dec_block(request.user)
            Schedule(request)
            return HttpResponse(status="302", content="/")
        except ObjectDoesNotExist:
            DBScheduleLock.dec_block(request.user)
            return bad_request(request, "Failed")

    if request.user.is_authenticated:
        DBScheduleLock.general_wait_for_unblock(request.user)
        if request.method == "POST":
            if request.POST["req"] == "put":
                ret = addEvent(request)
                return ret
            elif request.POST["req"] == "post":
                ret = editEvent(request)
                return ret
            elif request.POST["req"] == "delete":
                ret = deleteEvent(request)
                return ret
        DBScheduleLock.dec_block(request.user)
    raise PermissionDenied


def Task(request):
    """Various operations on tasks - get info, update info, create new, delete. Supports POST.
    Django does not support PUT or DELETE, at least easily, and so these are implemented with POST."""

    def addTask(request):
        # try:
        form = AddTaskForm(data=request.POST, user=request.user)
        if form.is_valid():
            CalAppTask(form.cleaned_data, request.user).save()
            DBScheduleLock.dec_block(request.user)
            Schedule(request)
            return HttpResponse(status="302", content="/")
        else:
            DBScheduleLock.dec_block(request.user)
            return render(request, "CalendarApp/AddTask.html", {'form': form})
        # except:
        #     return bad_request(request, "Failed")

    def editTask(request):
        logger = logging.getLogger("mylogger")
        # try:
        obj = CalAppModels.Task.objects.get(pk=request.POST["pk"])
        if request.POST["all"] == 'true':
            obj = obj.parent
            logger.info("Changing parent instead of just child")
        if not obj.owner == request.user:
            shares = CalAppModels.User_Task.objects.filter(user=request.user).filter(task=obj)
            if shares:
                form = EditSharedTaskForm(data=request.POST)
                if form.is_valid():
                    share = shares.first()
                    share.importance = request.POST["importance"]
                    share.save()
                    DBScheduleLock.dec_block(request.user)
                    Schedule(request)
                    return HttpResponse(status="302", content="/")
                else:
                    DBScheduleLock.dec_block(request.user)
                    return render(request, "CalendarApp/EditTask.html", {'form': form, "noDelete": 1})
            raise PermissionDenied
        form = EditTaskForm(data=request.POST, user=request.user)
        if form.is_valid():
            CalAppTask(form.cleaned_data, request.user).save(pk=obj.pk)
            DBScheduleLock.dec_block(request.user)
            Schedule(request)
            return HttpResponse(status="302", content="/")
        else:
            DBScheduleLock.dec_block(request.user)
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
        DBScheduleLock.dec_block(request.user)
        Schedule(request)
        return HttpResponse(status="302", content="/")
        # except:
        #     return bad_request(request, "Failed")

    if request.user.is_authenticated:
        DBScheduleLock.general_wait_for_unblock(request.user)
        if request.method == "POST":
            if request.POST["req"] == "put":
                ret = addTask(request)

                return ret
            elif request.POST["req"] == "post":
                ret = editTask(request)

                return ret
            elif request.POST["req"] == "delete":
                ret = deleteTask(request)

                return ret
        DBScheduleLock.dec_block(request.user)
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

    if owner2 in usersShared1:
        return True

    if type(calItem2) == CalAppModels.Task:
        shares = CalAppModels.User_Task.objects.filter(task=calItem2)
        usersShared2 = [share.user for share in shares]
    else:
        shares = CalAppModels.User_Event.objects.filter(task=calItem2)
        usersShared2 = [share.user for share in shares]

    if owner1 in usersShared2:
        return True
    return False


def _conflicting(calItem1, calItem2):
    begin1 = calItem1.begin_datetime
    begin2 = calItem2.begin_datetime
    if begin2 < begin1 < calItem2.end_datetime:
        if _related_by_user(calItem1, calItem2):
            return True
    elif begin1 < begin2 < calItem1.end_datetime:
        if _related_by_user(calItem1, calItem2):
            return True
    elif begin1 == begin2:
        if _related_by_user(calItem1, calItem2):
            return True
    return False


def _get_priority(calItem, user):
    due_date = calItem.due_date if type(calItem) == CalAppModels.Task else calItem.begin_datetime
    if calItem.owner == user:
        importance = calItem.owner_importance
    else:
        try:
            if type(calItem) == CalAppModels.Task:
                importance = CalAppModels.User_Task.objects.get(user=user, task=calItem).importance
            else:
                importance = CalAppModels.User_Event.objects.get(user=user, event=calItem).importance
        except ObjectDoesNotExist:
            importance = 0
    ret = (importance + 0.01) ** 1.1 \
        + ((make_aware(datetime.datetime.now()).toordinal() - due_date.toordinal()) + 0.01)
    return ret


def _get_constrainedness(calItem, now=make_aware(datetime.datetime.now())):
    if type(calItem) == CalAppModels.Task:
        numerator = (calItem.expected_minutes * 60) ** 1.1
        overdue = calItem.due_date < now
        if overdue:
            due_date = now + datetime.timedelta(hours=12)
        else:
            due_date = calItem.due_date
        denominator = max((due_date - max(calItem.available_date, now)).total_seconds(), 1)
        return numerator / denominator
    elif type(calItem) == CalAppModels.Event:
        return (calItem.end_datetime - calItem.begin_datetime).total_seconds() ** 1.5
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
        cal_item_stats.append([event,
                               averagePriority * constrainedness,
                               maxPriority * constrainedness,
                               constrainedness])

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
        cal_item_stats.append([task, averagePriority * constrainedness, maxPriority * constrainedness, constrainedness])
    return cal_item_stats


def _get_individual_cal_item_stats(cal_item_stats, when_is_now):
    if type(cal_item_stats[0]) == CalAppModels.Task:
        task = cal_item_stats[0]
        constrainedness = _get_constrainedness(task, when_is_now)
        return [task,
                cal_item_stats[1] * constrainedness / cal_item_stats[3],
                cal_item_stats[2] * constrainedness / cal_item_stats[3],
                constrainedness]
    elif type(cal_item_stats[0]) == CalAppModels.Event:
        event = cal_item_stats[0]
        constrainedness = _get_constrainedness(event, when_is_now)
        return [event,
                cal_item_stats[1] * constrainedness / cal_item_stats[3],
                cal_item_stats[2] * constrainedness / cal_item_stats[3],
                constrainedness]
    else:
        raise Exception("You passed in the wrong parameters!")


def _get_all_related_scheduling_info(user):
    logger = logging.getLogger("mylogger")
    all_events = set(CalAppModels.Event.objects.filter(owner=user, parent__isnull=False, exception=False))
    all_tasks = set(CalAppModels.Task.objects.filter(owner=user, parent__isnull=False, exception=False))
    all_event_shares = CalAppModels.User_Event.objects.filter(event__in=all_events)
    all_task_shares = set(CalAppModels.User_Task.objects.filter(task__in=all_tasks))
    all_related_users = {share.user for share in all_event_shares}
    all_related_users.add(user)
    for share in all_task_shares:
        all_related_users.add(share.user)
    for event in all_events:
        all_related_users.add(event.owner)
    for task in all_tasks:
        all_related_users.add(task.owner)
    new_num_users = len(all_related_users) - 1
    while new_num_users != 0:
        num_users = len(all_related_users)
        for related_user in all_related_users:
            all_events = all_events.union(set(CalAppModels.Event.objects.filter(owner=related_user,
                                                                                parent__isnull=False,
                                                                                exception=False)))
            all_tasks = all_tasks.union(set(CalAppModels.Task.objects.filter(owner=related_user,
                                                                             parent__isnull=False,
                                                                             exception=False)))
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
        all_events = all_events.union(set(CalAppModels.Event.objects.filter(owner=related_user,
                                                                            parent__isnull=False,
                                                                            exception=False)))
        all_tasks = all_tasks.union(set(CalAppModels.Task.objects.filter(owner=related_user,
                                                                         parent__isnull=False,
                                                                         exception=False)))
    return all_events, all_tasks, all_related_users


def _try_to_schedule_before(item_to_schedule, scheduled, time_to_schedule_before, tick, allowed_time):
    item_to_schedule_obj = item_to_schedule[0]
    item_to_schedule_expected_minutes = item_to_schedule_obj.expected_minutes
    interval = 480
    right_now = make_aware(datetime.datetime.now())
    success = False
    to_remove = []
    item_to_schedule_obj.begin_datetime = max(right_now, item_to_schedule_obj.available_date)
    item_to_schedule_obj.end_datetime = item_to_schedule_obj.begin_datetime \
                                     + datetime.timedelta(minutes=item_to_schedule_expected_minutes)
    while interval > min(5, item_to_schedule_expected_minutes // 5) and not success:
        if time.time() - tick > allowed_time:
            return False, []
        conflict = False
        for item in scheduled:
            item_obj = item[0]
            if _conflicting(item_obj, item_to_schedule_obj):
                conflict = True
                item_day_datetime = make_aware(datetime.datetime.combine(item_obj.begin_datetime.date(), datetime.datetime.min.time()))
                to_schedule_day_datetime = make_aware(datetime.datetime.combine(item_to_schedule_obj.begin_datetime.date(), datetime.datetime.min.time()))
                new_item_stats = _get_individual_cal_item_stats(item, item_day_datetime)
                new_item_to_schedule_stats = _get_individual_cal_item_stats(item_to_schedule,
                                                                            to_schedule_day_datetime)
                if new_item_stats[1] + new_item_stats[2] * 0.1 \
                        < new_item_to_schedule_stats[1] + new_item_to_schedule_stats[2] * 0.1:
                    if item not in to_remove:
                        to_remove.append(item)
        if conflict:
            item_to_schedule_obj.begin_datetime += datetime.timedelta(minutes=interval)
            item_to_schedule_obj.end_datetime += datetime.timedelta(minutes=interval)
        else:
            item_to_schedule[0].scheduled = True
            scheduled.append(item_to_schedule)
            success = True
            return success, []
        if item_to_schedule_obj.end_datetime > time_to_schedule_before:
            interval //= 2
            item_to_schedule_obj.begin_datetime = max(right_now, item_to_schedule_obj.available_date)
            item_to_schedule_obj.end_datetime = item_to_schedule_obj.begin_datetime + \
                                               datetime.timedelta(minutes=item_to_schedule_expected_minutes)

    return success, to_remove


def _add_task_to_schedule(item_to_schedule, scheduled, tick, allowed_time):
    global print_level
    item_to_schedule_due_date = item_to_schedule[0].due_date
    print_level += 1
    indent = "    " * print_level
    logger = logging.getLogger("mylogger")
    right_now = make_aware(datetime.datetime.now())
    logger.info(indent + "Now attempting to schedule task before due date")
    success, to_remove = _try_to_schedule_before(item_to_schedule,
                                                 scheduled,
                                                 item_to_schedule_due_date,
                                                 tick,
                                                 allowed_time)
    if to_remove and not success:
        logger.info(indent + "I was unsuccessful, and I think it may be because some other items need to be removed.")
        logger.info(indent + "Removing those other items...")
        for item in to_remove:
            item[0].scheduled = False
            scheduled.remove(item)
        logger.info(indent + "Trying again to schedule before due date")
        success, _ = _try_to_schedule_before(item_to_schedule,
                                             scheduled,
                                             item_to_schedule_due_date,
                                             tick,
                                             allowed_time)
        if not success:
            logger.info(indent + "Unsuccessful; replacing removed items")
            for item in to_remove:
                item[0].scheduled = True
                scheduled.append(item)
            to_remove = []
        else:
            logger.info(indent + "Success!")
            print_level -= 1
            return success, to_remove
    hourIncrement = 24
    if not success:
        logger.info(indent + "First attempts were unsuccessful.")
    while (hourIncrement <= 72) and (not success):
        logger.info(indent + "Now attempting to schedule within " + str(hourIncrement) + " hours after its due date.")
        success, to_remove = _try_to_schedule_before(item_to_schedule,
                                                     scheduled,
                                                     max(item_to_schedule_due_date, right_now) + datetime.timedelta(hours=hourIncrement),
                                                     tick, allowed_time)
        if to_remove and not success:
            logger.info(indent + "I was unsuccessful, and I think it may be because some other items need to be removed.")
            logger.info(indent + "Removing those other items...")
            for item in to_remove:
                item[0].scheduled = False
                scheduled.remove(item)
            logger.info(indent + "Trying again to schedule within " + str(hourIncrement) + " hours after its due date.")
            success, _ = _try_to_schedule_before(item_to_schedule, scheduled,
                                                 max(item_to_schedule_due_date, right_now) + datetime.timedelta(hours=hourIncrement),
                                                 tick, allowed_time)
            if not success:
                logger.info(indent + "Unsuccessful; replacing removed items")
                for item in to_remove:
                    item[0].scheduled = True
                    scheduled.append(item)
                to_remove = []
            else:
                logger.info(indent + "Success!")
                print_level -= 1
                return success, to_remove
        hourIncrement += 24
    print_level -= 1
    return success, to_remove


def _add_event_to_schedule(item_to_schedule, scheduled, tick, allowed_time):
    global print_level
    item_to_schedule_obj = item_to_schedule[0]
    print_level += 1
    indent = "    " * print_level
    logger = logging.getLogger("mylogger")
    to_remove = []
    removed_items = []
    for item in scheduled:
        item_obj = item[0]
        conflict = _conflicting(item_obj, item_to_schedule_obj)
        if conflict:
            logger.info(indent + "Found a conflict")
            if type(item_obj) == CalAppModels.Task:
                logger.info(indent + "Conflict is with " + item_obj.task_text + ", id " + str(item_obj.pk) + ", a task, so I'm removing it temporarily.")
                to_remove.append(item)
            else:
                logger.info(
                    indent + "Conflict is with " + item_obj.task_text + ", an event.")
                item_day_datetime = make_aware(datetime.datetime.combine(item_obj.begin_datetime.date(), datetime.datetime.min.time()))
                to_schedule_day_datetime = make_aware(datetime.datetime.combine(item_to_schedule_obj.begin_datetime.date(),
                                                                     datetime.datetime.min.time()))
                new_item_stats = _get_individual_cal_item_stats(item, item_day_datetime)
                new_item_to_schedule_stats = _get_individual_cal_item_stats(item_to_schedule,
                                                                            to_schedule_day_datetime)
                if new_item_to_schedule_stats[1] + new_item_to_schedule_stats[2] * 0.1 > new_item_stats[1] + new_item_stats[2] * 0.1:
                    logger.info(indent + "The item to schedule is more important, so I'm removing the other.")
                    to_remove.append(item)
                else:
                    logger.info(indent + "The other item is more important. Removing this.")
                    print_level -= 1
                    return False, []

    logger.info(indent + "Adding the item to the schedule")

    item_to_schedule[0].scheduled = True
    scheduled.append(item_to_schedule)
    for item in to_remove:
        item[0].scheduled = False
        scheduled.remove(item)

    overall_success = True

    logger.info(indent + "Starting round 1 of rescheduling removed items.")

    for i in range(len(to_remove) - 1, -1, -1):  # backwards to ensure removing items works
        item = to_remove[i]
        item_obj = item[0]
        if type(item_obj) == CalAppModels.Task:
            logger.info(indent + "Item is a task: " + item_obj.task_text)
            logger.info(indent + "Attempt to reschedule...")
            success, _ = _try_to_schedule_before(item, scheduled, item_obj.due_date, tick, allowed_time)
            if not success:
                logger.info(indent + "Fail")
                item_day_datetime = make_aware(datetime.datetime.combine(item_obj.begin_datetime.date(), datetime.datetime.min.time()))
                to_schedule_day_datetime = make_aware(datetime.datetime.combine(item_to_schedule_obj.begin_datetime.date(),
                                                                     datetime.datetime.min.time()))
                new_item_stats = _get_individual_cal_item_stats(item, item_day_datetime)
                new_item_to_schedule_stats = _get_individual_cal_item_stats(item_to_schedule,
                                                                            to_schedule_day_datetime)
                if not (new_item_to_schedule_stats[1] + new_item_to_schedule_stats[2] * 0.1
                        > new_item_stats[1] + new_item_stats[2] * 0.1):
                    logger.info(indent + "The other item was more important, so I have to unschedule myself.")
                    overall_success = False
                    item_to_schedule[0].scheduled = False
                    scheduled.remove(item_to_schedule)
                    break
                else:
                    logger.info(indent + "It's ok - I was more important")
            else:
                logger.info(indent + "Success")
                to_remove.remove(item)
                item_obj.save()
        else:
            logger.info(indent + "Item is an event. Cannot be rescheduled.")
    logger.info(indent + "Starting round 2 of rescheduling removed items.")
    for item in to_remove:
        item_obj = item[0]
        if type(item_obj) == CalAppModels.Task:
            logger.info(indent + "Item is a task: " + item_obj.task_text)
            logger.info(indent + "Attempt to reschedule...")
            success, _ = _try_to_schedule_before(item, scheduled, item_obj.due_date, tick, allowed_time)
        else:
            logger.info(indent + "Item is an event. Cannot be rescheduled.")
        if not success:
            logger.info(indent + "Failed to reschedule removed item.")
            removed_items.append(item)
        else:
            logger.info(indent + "Rescheduled previously removed item.")
            item_obj.save()
    print_level -= 1
    return overall_success, removed_items


def _schedule_user_slow(user):
    global _user_queue
    slow_allowed_time = 900
    logger = logging.getLogger("mylogger")
    tick = time.time()
    right_now = make_aware(datetime.datetime.now())
    all_events, all_tasks, all_related_users = _get_all_related_scheduling_info(user)

    cal_item_stats = sorted(_get_cal_item_stats(all_events, all_tasks, all_related_users),
                            key=lambda a: a[1] + a[2] * 0.1)
    scheduled = []
    unscheduled = []
    for item in cal_item_stats:
        item_obj = item[0]
        if type(item_obj) == CalAppModels.Task and \
                (item_obj.begin_datetime < right_now or
                 item_obj.end_datetime > item_obj.due_date or
                 item_obj.begin_datetime.date() > max(right_now.date(), item_obj.available_date.date())):
            item[0].scheduled = False
            item[0].save()
        if item_obj.scheduled:
            conflict = False
            for item2 in scheduled:
                conflict |= _conflicting(item_obj, item2[0])
            if conflict:
                item[0].scheduled = False
                item_obj.save()
                unscheduled.append(item)
            else:
                scheduled.append(item)
        else:
            unscheduled.append(item)


    while (time.time() - tick < slow_allowed_time) and len(unscheduled) > 0:
        for r_user in all_related_users:
            obj = CalAppModels.User_Schedule_Lock.objects.get(user=r_user)
            if obj.num_waiting > 0:
                return False
        logger.info("**************" + str(slow_allowed_time - (time.time() - tick)) + "seconds left")
        item_to_schedule = unscheduled.pop(-1)
        item_to_schedule_obj = item_to_schedule[0]
        if type(item_to_schedule_obj) == CalAppModels.Task:
            logger.info("Attempting to add" + item_to_schedule_obj.task_text + ", " + str(item_to_schedule_obj.due_date))
            success, removed_items = _add_task_to_schedule(item_to_schedule, scheduled, tick, slow_allowed_time)
        else:
            logger.info("Attempting to add" + item_to_schedule_obj.event_text)
            success, removed_items = _add_event_to_schedule(item_to_schedule, scheduled, tick, slow_allowed_time)
        if removed_items:
            logger.info("Removed" + str(removed_items) + "during the attempt")
            for item in removed_items:
                unscheduled.insert(len(unscheduled) // 2, item)
                item[0].scheduled = False
                while item in scheduled:
                    logger.info("!!!!!!!!!!Item was somehow still in scheduled list???")
                    scheduled.remove(item)
                item[0].save()
        if success:
            logger.info("Succeeded")
        else:
            logger.info("Failed")
        item_to_schedule_obj.save()
    logger.info("Finished slow schedule")
    now = right_now + datetime.timedelta(seconds=slow_allowed_time)
    for r_user in all_related_users:
        try:
            schedule_info = CalAppModels.User_Schedule_Info.objects.get(user=r_user)
            schedule_info.last_slow_schedule = now
            schedule_info.last_fast_schedule = now
            schedule_info.save()
        except ObjectDoesNotExist:
            schedule_info = CalAppModels.User_Schedule_Info(user=r_user, last_fast_schedule=now, last_slow_schedule=now)
            schedule_info.save()
        if r_user in _user_queue:
            _user_queue.remove(user)
    return True

print_level = 0


def _schedule_user_quick_2(user):
    global print_level
    fast_allowed_time = 30
    logger = logging.getLogger("mylogger")
    tick = time.time()
    right_now = make_aware(datetime.datetime.now())
    all_events, all_tasks, all_related_users = _get_all_related_scheduling_info(user)

    DBScheduleLock.lock.acquire()
    for r_user in all_related_users:
        try:
            obj = CalAppModels.User_Schedule_Lock.objects.get(user=r_user)
        except ObjectDoesNotExist:
            obj = CalAppModels.User_Schedule_Lock(user=r_user, block_all=0, num_waiting=0)
        obj.num_waiting += 1
        obj.save()
    DBScheduleLock.lock.release()
    while 1:
        fail = False
        DBScheduleLock.lock.acquire()
        for r_user in all_related_users:
            obj = CalAppModels.User_Schedule_Lock.objects.get(user=r_user)
            if obj.block_all != 0:
                fail = True
                break
        if fail:
            DBScheduleLock.lock.release()
            time.sleep(random.uniform(0.05, 0.5))
        else:
            for r_user in all_related_users:
                obj = CalAppModels.User_Schedule_Lock.objects.get(user=r_user)
                obj.num_waiting -= 1
                obj.block_all += 1
                obj.save()
            DBScheduleLock.lock.release()
            break

    cal_item_stats = sorted(_get_cal_item_stats(all_events, all_tasks, all_related_users),
                            key=lambda a: a[1] + a[2] * 0.1)
    scheduled = []
    unscheduled = []
    for item in cal_item_stats:
        item_obj = item[0]
        if type(item_obj) == CalAppModels.Task and \
                (item_obj.begin_datetime < right_now or
                 item_obj.end_datetime > item_obj.due_date or
                 (item_obj.begin_datetime.date() > max(right_now.date(), item_obj.available_date.date())
                  and item_obj.begin_datetime > right_now + datetime.timedelta(days=7))):
            item[0].scheduled = False
            item_obj.save()
        if item_obj.scheduled:
            conflict = False
            for item2 in scheduled:
                conflict |= _conflicting(item_obj, item2[0])
            if conflict:
                item[0].scheduled = False
                item_obj.save()
                unscheduled.append(item)
            else:
                scheduled.append(item)
        else:
            unscheduled.append(item)

    while (time.time() - tick < fast_allowed_time) and len(unscheduled) > 0:
        logger.info("    " * print_level + "************** " + str(fast_allowed_time - (time.time() - tick)) + " seconds left")
        item_to_schedule = unscheduled.pop(-1)
        item_to_schedule_obj = item_to_schedule[0]
        if type(item_to_schedule_obj) == CalAppModels.Task:
            logger.info("    " * print_level + "Attempting to add " + item_to_schedule_obj.task_text + ", " + str(item_to_schedule_obj.due_date))

            success, removed_items = _add_task_to_schedule(item_to_schedule, scheduled, tick, fast_allowed_time)
        else:
            logger.info("    " * print_level + "Attempting to add " + item_to_schedule_obj.event_text)
            success, removed_items = _add_event_to_schedule(item_to_schedule, scheduled, tick, fast_allowed_time)
        if removed_items:
            tick += len(removed_items)
            logger.info("    " * print_level + "Removed " + str(removed_items) + " during the attempt")
            for item in removed_items:
                unscheduled.append(item)
                item[0].scheduled = False
                while item in scheduled:
                    logger.info("!!!!!!!!!!!!!!!! Item was somehow still in scheduled list???")
                    scheduled.remove(item)
                item[0].save()
                unscheduled = sorted(unscheduled, key=lambda a: a[1] + a[2] * 0.1)
        if success:
            logger.info("    " * print_level + "Succeeded")
        else:
            logger.info("    " * print_level + "Failed")
        item_to_schedule_obj.save()
    DBScheduleLock.lock.acquire()
    for r_user in all_related_users:
        try:
            schedule_info = CalAppModels.User_Schedule_Info.objects.get(user=r_user)
            schedule_info.last_fast_schedule = right_now
            schedule_info.save()
        except ObjectDoesNotExist:
            schedule_info = CalAppModels.User_Schedule_Info(user=r_user, last_fast_schedule=right_now, last_slow_schedule=right_now)
            schedule_info.save()
        obj = CalAppModels.User_Schedule_Lock.objects.get(user=r_user)
        obj.block_all -= 1
        obj.save()
    DBScheduleLock.lock.release()



def Schedule(request):
    """Causes the schedule to run. Supports POST."""
    global _schedule_main_loop_is_running
    if not _schedule_main_loop_is_running:
        thread = threading.Thread(target=_scheduling_main_loop)
        thread.start()
        _schedule_main_loop_is_running = True
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
        try:
            schedule_info = CalAppModels.User_Schedule_Info.objects.get(user=request.user)
        except ObjectDoesNotExist:
            schedule_info = None
        if schedule_info \
                and (make_aware(datetime.datetime.now()) - datetime.timedelta(minutes=15)
                     < schedule_info.last_slow_schedule
                     or make_aware(datetime.datetime.now()) - datetime.timedelta(minutes=15)
                     < schedule_info.last_fast_schedule):
            needs_scheduling = False
        else:
            needs_scheduling = True
        DBScheduleLock.general_wait_for_unblock(request.user)
        eventsOwned = CalAppModels.Event.objects.filter(owner=request.user,
                                                        exception=False,
                                                        scheduled=True,
                                                        parent__isnull=False)
        unscheduled_events = CalAppModels.Event.objects.filter(owner=request.user,
                                                               exception=False,
                                                               scheduled=False,
                                                               parent__isnull=False)
        tasksOwned = CalAppModels.Task.objects.filter(owner=request.user,
                                                      exception=False,
                                                      scheduled=True,
                                                      parent__isnull=False)
        unscheduled_tasks = CalAppModels.Task.objects.filter(owner=request.user,
                                                             exception=False,
                                                             scheduled=False,
                                                             parent__isnull=False)
        event_shares = CalAppModels.User_Event.objects.filter(user=request.user)
        task_shares = CalAppModels.User_Task.objects.filter(user=request.user)
        eventsSharedSet = {share.event for share in event_shares}
        tasksSharedSet = {share.task for share in task_shares}
        eventPKs = {event.pk for event in eventsSharedSet}
        taskPKs = {task.pk for task in tasksSharedSet}
        eventsShared = CalAppModels.Event.objects.filter(pk__in=eventPKs,
                                                         exception=False,
                                                         scheduled=True,
                                                         parent__isnull=False)
        unscheduled_events = unscheduled_events.union(CalAppModels.Event.objects.filter(pk__in=eventPKs,
                                                                                        exception=False,
                                                                                        scheduled=False,
                                                                                        parent__isnull=False))
        tasksShared = CalAppModels.Task.objects.filter(pk__in=taskPKs,
                                                       exception=False,
                                                       scheduled=True,
                                                       parent__isnull=False)
        unscheduled_tasks = unscheduled_tasks.union(CalAppModels.Task.objects.filter(pk__in=taskPKs,
                                                                                     exception=False,
                                                                                     scheduled=False,
                                                                                     parent__isnull=False))
        calendars_shared_with_me = CalAppModels.Cal_Share.objects.filter(sharee=request.user, status="viewed")
        users_sharing_calendars_with_me = {calendar.sharer for calendar in calendars_shared_with_me}
        events_in_calendars_shared_with_me = set()
        tasks_in_calendars_shared_with_me = set()
        for user in users_sharing_calendars_with_me:
            events = CalAppModels.Event.objects.filter(owner=user,
                                                       exception=False,
                                                       scheduled=True,
                                                       parent__isnull=False)
            tasks = CalAppModels.Task.objects.filter(owner=user,
                                                     exception=False,
                                                     scheduled=True,
                                                     parent__isnull=False)
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
        DBScheduleLock.dec_block(request.user)
    else:
        eventsOwned = set()
        eventsShared = set()
        events_in_calendars_shared_with_me = set()
        tasksOwned = set()
        tasksShared = set()
        tasks_in_calendars_shared_with_me = set()
        unscheduled_events = set()
        unscheduled_tasks = set()
        needs_scheduling = False

    repeatForm = RepetitionForm()
    return render(request, "CalendarApp/index.html", {"eventsOwned": eventsOwned,
                                                      "eventsShared": eventsShared,
                                                      "eventsInViewedCalendars": events_in_calendars_shared_with_me,
                                                      "tasksOwned": tasksOwned,
                                                      "tasksShared": tasksShared,
                                                      "tasksInViewedCalendars": tasks_in_calendars_shared_with_me,
                                                      "repeatForm": repeatForm,
                                                      "unscheduled_events": unscheduled_events,
                                                      "unscheduled_tasks": unscheduled_tasks,
                                                      "needs_scheduling": needs_scheduling})


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
    if request.user.is_authenticated:
        DBScheduleLock.general_wait_for_unblock(request.user)
        # try:
        obj = CalAppModels.Event.objects.get(pk=request.GET["pk"])
        shares = CalAppModels.User_Event.objects.filter(event=obj)
        shared_users = {share.user for share in shares}
        numSiblings = len(CalAppModels.Event.objects.filter(parent=obj.parent)) - 1
        # except:
        #     DBScheduleLock.dec_block(request.user)
        #     return bad_request(request, "Failed")
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
            DBScheduleLock.dec_block(request.user)
            return render(request,
                          "CalendarApp/editevent.html",
                          {"form": form,
                           "pk": request.GET["pk"],
                           "type": request.GET["type"],
                           "hasSiblings": numSiblings > 0})
        share = CalAppModels.User_Event.objects.filter(user=request.user).filter(event=obj)
        if share:
            form = EditSharedEventForm(data={"importance": share.first().importance, "pk": request.GET["pk"]})
            DBScheduleLock.dec_block(request.user)
            return render(request,
                          "CalendarApp/editevent.html",
                          {"form": form, "pk": request.GET["pk"], "type": request.GET["type"], "noDelete": True})
        DBScheduleLock.dec_block(request.user)
    raise PermissionDenied


def EditTask(request):
    if request.user.is_authenticated:
        DBScheduleLock.general_wait_for_unblock(request.user)
        try:
            obj = CalAppModels.Task.objects.get(pk=request.GET["pk"])
            shares = CalAppModels.User_Task.objects.filter(task=obj)
            shared_users = {share.user for share in shares}
            numSiblings = len(CalAppModels.Task.objects.filter(parent=obj.parent)) - 1
        except ObjectDoesNotExist:
            DBScheduleLock.dec_block(request.user)
            return bad_request(request, "Failed")
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
            DBScheduleLock.dec_block(request.user)
            return render(request,
                          "CalendarApp/edittask.html",
                          {"form": form,
                           "pk": request.GET["pk"],
                           "type": request.GET["type"],
                           "hasSiblings": numSiblings > 0})
        share = CalAppModels.User_Task.objects.filter(user=request.user).filter(task=obj)
        if share:
            form = EditSharedTaskForm(data={"importance": share.first().importance, "pk": request.GET["pk"]})
            DBScheduleLock.dec_block(request.user)
            return render(request,
                          "CalendarApp/edittask.html",
                          {"form": form, "pk": request.GET["pk"], "type": request.GET["type"], "noDelete": True})
        DBScheduleLock.dec_block(request.user)
    raise PermissionDenied


def Contacts(request):
    if request.user.is_authenticated:
        if request.method == "GET":
            return _render_contacts_form(request)
        elif request.method == "POST":
            try:
                otherUser = CalAppModels.User.objects.get(username=request.POST["add_contact"])
            except ObjectDoesNotExist:
                return bad_request(request, "Failed")
            if otherUser == request.user:
                return bad_request(request, "Failed")
            try:
                contactObj = CalAppModels.Contact.objects.filter(user1=request.user).get(user2=otherUser)
            except ObjectDoesNotExist:
                try:
                    contactObj = CalAppModels.Contact.objects.filter(user2=request.user).get(user1=otherUser)
                except ObjectDoesNotExist:
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
        except ObjectDoesNotExist:
            return bad_request(request, "Failed")
        try:
            contactObj = CalAppModels.Contact.objects.filter(user1=request.user).get(user2=otherUser)
        except ObjectDoesNotExist:
            try:
                contactObj = CalAppModels.Contact.objects.filter(user2=request.user).get(user1=otherUser)
            except ObjectDoesNotExist:
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
        except ObjectDoesNotExist:
            return bad_request(request, "Failed")
    raise PermissionDenied


def CalShareToggle(request):
    if request.user.is_authenticated:
        try:
            sharee = CalAppModels.User.objects.get(pk=request.POST['pk'])
        except ObjectDoesNotExist:
            return bad_request(request, "Failed")
        try:
            cal_share = CalAppModels.Cal_Share.objects.get(sharer=request.user, sharee=sharee)
            cal_share.delete()
        except ObjectDoesNotExist:
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
        except ObjectDoesNotExist:
            return bad_request(request, "Failed")
        try:
            cal_share = CalAppModels.Cal_Share.objects.get(sharer=sharer, sharee=request.user)
            if cal_share.status == "viewed":
                cal_share.status = "not viewed"
            else:
                cal_share.status = "viewed"
            cal_share.save()
        except ObjectDoesNotExist:
            return bad_request(request, "Failed")
        return _render_contacts_form(request)
    else:
        raise PermissionDenied
