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
        else:
            logger.info(_user_queue)
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
    if calItem2.begin_datetime < calItem1.begin_datetime < calItem2.end_datetime:
        if _related_by_user(calItem1, calItem2):
            return True
    elif calItem1.begin_datetime < calItem2.begin_datetime < calItem1.end_datetime:
        if _related_by_user(calItem1, calItem2):
            return True
    elif calItem1.begin_datetime == calItem2.begin_datetime:
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
    logger.info("Getting related scheduling info....")
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
        logger.info("Have to loop...")
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
    logger.info("Done!")
    return all_events, all_tasks, all_related_users


def _try_to_schedule_before(item_to_schedule, scheduled, time_to_schedule_before, tick, allowed_time):
    interval = 480
    right_now = datetime.datetime.now()
    success = False
    to_remove = []
    item_to_schedule[0].begin_datetime = max(make_aware(right_now), item_to_schedule[0].available_date)
    item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime \
                                     + datetime.timedelta(minutes=item_to_schedule[0].expected_minutes)
    while interval > min(5, item_to_schedule[0].expected_minutes // 5) and not success:
        if time.time() - tick > allowed_time:
            return False, []
        conflict = False
        for item in scheduled:
            if _conflicting(item[0], item_to_schedule[0]):
                conflict = True
                new_item_stats = _get_individual_cal_item_stats(item, item[0].begin_datetime)
                new_item_to_schedule_stats = _get_individual_cal_item_stats(item_to_schedule,
                                                                            item_to_schedule[0].begin_datetime)
                if new_item_stats[1] + new_item_stats[2] * 0.1 \
                        < new_item_to_schedule_stats[1] + new_item_to_schedule_stats[2] * 0.1:
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
            item_to_schedule[0].end_datetime = item_to_schedule[0].begin_datetime + \
                                               datetime.timedelta(minutes=item_to_schedule[0].expected_minutes)
        else:
            pass

    return success, to_remove


def _add_task_to_schedule(item_to_schedule, scheduled, tick, allowed_time):
    logger = logging.getLogger("mylogger")
    right_now = datetime.datetime.now()
    logger.info("attempting to add the item before its due date, first try")
    success, to_remove = _try_to_schedule_before(item_to_schedule,
                                                 scheduled,
                                                 item_to_schedule[0].due_date,
                                                 tick,
                                                 allowed_time)
    if to_remove and not success:
        for item in to_remove:
            item[0].scheduled = False
            scheduled.remove(item)
        logger.info("Fail, removed items. Second try.")
        success, _ = _try_to_schedule_before(item_to_schedule,
                                             scheduled,
                                             item_to_schedule[0].due_date,
                                             tick,
                                             allowed_time)
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
            success, to_remove = _try_to_schedule_before(item_to_schedule,
                                                         scheduled,
                                                         make_aware(right_now +
                                                                    datetime.timedelta(hours=hourIncrement)),
                                                         tick, allowed_time)
            if to_remove and not success:
                for item in to_remove:
                    item[0].scheduled = False
                    scheduled.remove(item)
                success, _ = _try_to_schedule_before(item_to_schedule, scheduled,
                                                     make_aware(right_now + datetime.timedelta(hours=hourIncrement)),
                                                     tick, allowed_time)
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


def _add_event_to_schedule(item_to_schedule, scheduled, tick, allowed_time):
    logger = logging.getLogger("mylogger")
    to_remove = []
    removed_items = []
    for item in scheduled:
        conflict = _conflicting(item[0], item_to_schedule[0])
        if conflict:
            if type(item[0]) == CalAppModels.Task:
                logger.info("Conflict found with:" + str(item[0].task_text))
                logger.info("Trying to reschedule the other")
                to_remove.append(item)
            else:
                logger.info("Conflict found with:", item[0].event_text)
                new_item_stats = _get_individual_cal_item_stats(item, item[0].begin_datetime)
                new_item_to_schedule_stats = _get_individual_cal_item_stats(item_to_schedule,
                                                                            item_to_schedule[0].begin_datetime)
                if new_item_to_schedule_stats[1] + new_item_to_schedule_stats[2] * 0.1 > new_item_stats[1] + new_item_stats[2] * 0.1:
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

    for i in range(len(to_remove) - 1, -1, -1):  # backwards to ensure removing items works
        item = to_remove[i]
        logger.info("Trying to reschedule an item...")
        if type(item[0]) == CalAppModels.Task:
            logger.info("The item is a task")
            success, _ = _try_to_schedule_before(item, scheduled, item[0].due_date, tick, allowed_time)
            if not success:
                logger.info("One of them failed to reschedule once I was put in")
                new_item_stats = _get_individual_cal_item_stats(item, item[0].begin_datetime)
                new_item_to_schedule_stats = _get_individual_cal_item_stats(item_to_schedule,
                                                                            item_to_schedule[0].begin_datetime)
                if new_item_to_schedule_stats[1] + new_item_to_schedule_stats[2] * 0.1 \
                        > new_item_stats[1] + new_item_stats[2] * 0.1:
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
            success, _ = _try_to_schedule_before(item, scheduled, item[0].due_date, tick, allowed_time)
        else:
            logger.info("This one is an event")
            success, removed = _add_event_to_schedule(item, scheduled, tick, allowed_time)
            removed_items.append += removed
        if not success:
            logger.info("Unsuccessful in rescheduling this item")
            removed_items.append(item)
        else:
            item[0].save()
    return overall_success, removed_items


def _schedule_user_slow(user):
    global _user_queue
    slow_allowed_time = 900
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
                (item[0].begin_datetime < make_aware(right_now) or
                 item[0].end_datetime > item[0].due_date or
                 item[0].begin_datetime.date() > max(make_aware(right_now).date(), item[0].available_date.date())):
            item[0].scheduled = False
            item[0].save()
        if item[0].scheduled:
            conflict = False
            for item2 in scheduled:
                conflict |= _conflicting(item[0], item2[0])
            if conflict:
                item[0].scheduled = False
                item[0].save()
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
        if type(item_to_schedule[0]) == CalAppModels.Task:
            logger.info("Attempting to add" + item_to_schedule[0].task_text + ", " + str(item_to_schedule[0].due_date))
            success, removed_items = _add_task_to_schedule(item_to_schedule, scheduled, tick, slow_allowed_time)
        else:
            logger.info("Attempting to add" + item_to_schedule[0].event_text)
            success, removed_items = _add_event_to_schedule(item_to_schedule, scheduled, tick, slow_allowed_time)
        if removed_items:
            logger.info("Removed" + str(removed_items) + "during the attempt")
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
    logger.info("Finished slow schedule")
    logger.info("all_related_users: " + str(all_related_users))
    logger.info("queue before removing users:" + str(_user_queue))
    now = make_aware(right_now) + datetime.timedelta(seconds=slow_allowed_time)
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
    logger.info("queue after removing users:" + str(_user_queue))
    return True


def _schedule_user_quick_2(user):
    logger = logging.getLogger("mylogger")
    tick = time.time()
    right_now = datetime.datetime.now()
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
                logger.info("You didn't check if some other thread took care of it!")
                obj.block_all += 1
                obj.save()
            DBScheduleLock.lock.release()
            break

    cal_item_stats = sorted(_get_cal_item_stats(all_events, all_tasks, all_related_users),
                            key=lambda a: a[1] + a[2] * 0.1)
    scheduled = []
    unscheduled = []
    for item in cal_item_stats:
        if type(item[0]) == CalAppModels.Task and \
                (item[0].begin_datetime < make_aware(right_now) or
                 item[0].end_datetime > item[0].due_date or
                 item[0].begin_datetime.date() > max(make_aware(right_now).date(), item[0].available_date.date())):
            item[0].scheduled = False
            item[0].save()
        if item[0].scheduled:
            conflict = False
            for item2 in scheduled:
                conflict |= _conflicting(item[0], item2[0])
            if conflict:
                item[0].scheduled = False
                item[0].save()
                unscheduled.append(item)
            else:
                scheduled.append(item)
        else:
            unscheduled.append(item)

    while (time.time() - tick < 30) and len(unscheduled) > 0:
        logger.info("**************" + str(30 - (time.time() - tick)) + "seconds left")
        item_to_schedule = unscheduled.pop(-1)
        if type(item_to_schedule[0]) == CalAppModels.Task:
            logger.info("Attempting to add" + item_to_schedule[0].task_text + ", " + str(item_to_schedule[0].due_date))
            success, removed_items = _add_task_to_schedule(item_to_schedule, scheduled, tick, 30)
        else:
            logger.info("Attempting to add" + item_to_schedule[0].event_text)
            success, removed_items = _add_event_to_schedule(item_to_schedule, scheduled, tick, 30)
        if removed_items:
            logger.info("Removed" + str(removed_items) + "during the attempt")
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
    DBScheduleLock.lock.acquire()
    now = make_aware(right_now)
    for r_user in all_related_users:
        try:
            schedule_info = CalAppModels.User_Schedule_Info.objects.get(user=r_user)
            schedule_info.last_fast_schedule = now
            schedule_info.save()
        except ObjectDoesNotExist:
            schedule_info = CalAppModels.User_Schedule_Info(user=r_user, last_fast_schedule=now, last_slow_schedule=now)
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
            pass
        else:
            Schedule(request)
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
    else:
        eventsOwned = set()
        eventsShared = set()
        events_in_calendars_shared_with_me = set()
        tasksOwned = set()
        tasksShared = set()
        tasks_in_calendars_shared_with_me = set()
        unscheduled_events = set()
        unscheduled_tasks = set()

    repeatForm = RepetitionForm()
    DBScheduleLock.dec_block(request.user)
    return render(request, "CalendarApp/index.html", {"eventsOwned": eventsOwned,
                                                      "eventsShared": eventsShared,
                                                      "eventsInViewedCalendars": events_in_calendars_shared_with_me,
                                                      "tasksOwned": tasksOwned,
                                                      "tasksShared": tasksShared,
                                                      "tasksInViewedCalendars": tasks_in_calendars_shared_with_me,
                                                      "repeatForm": repeatForm,
                                                      "unscheduled_events": unscheduled_events,
                                                      "unscheduled_tasks": unscheduled_tasks})


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
