from . import models as CalAppModels
from django.utils import timezone
from math import log2
from copy import deepcopy
import datetime


class CalendarItem:
    def __init__(self, info, user):
        self.info = info
        self.owner = user


class Event(CalendarItem):
    def parseWeeklyDays(self, num):
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

    def create_shares(self, event_obj):
        if self.info["shares"]:
            for share in self.info["shares"]:
                user_event_obj = CalAppModels.User_Event(event=event_obj,
                                                         user=share,
                                                         importance=event_obj.owner_importance,
                                                         status="invited")
                user_event_obj.save()
        saved_shares = CalAppModels.User_Event.objects.filter(event=event_obj)
        for saved_share in saved_shares:
            if saved_share.user not in self.info["shares"]:
                saved_share.delete()

    def save(self, pk=None):
        if pk:
            event_obj = CalAppModels.Event.objects.get(pk=pk)
            event_obj.event_text = self.info["text"]
            event_obj.begin_datetime = self.info["begin_datetime"]
            event_obj.end_datetime = self.info["end_datetime"]
            event_obj.owner_importance = self.info["owner_importance"]
            event_obj.repetition_type = self.info["repetition_type"]
            event_obj.repetition_number = self.info["repetition_number"]
            event_obj.from_date = self.info["from_date"]
            event_obj.until_date = self.info["until_date"]
            if event_obj.parent:
                event_obj.exception = True  # Because the child was changed independently of the parent
                temp = self.info["repetition_type"]
                self.info["repetition_type"] = "none"
                self.info["exception_child"] = event_obj
                Event(self.info, self.owner).save()
                self.info["exception_child"] = None
                self.info["repetition_type"] = temp
            event_obj.save()

            if not event_obj.parent:
                self._repeat(event_obj)
        else:
            event_obj = CalAppModels.Event(event_text=self.info["text"],
                                           begin_datetime=self.info["begin_datetime"],
                                           end_datetime=self.info["end_datetime"],
                                           owner=self.owner,
                                           owner_importance=self.info["owner_importance"],
                                           repetition_type=self.info["repetition_type"],
                                           repetition_number=self.info["repetition_number"],
                                           from_date=self.info["from_date"],
                                           until_date=self.info["until_date"],
                                           exception=False,
                                           scheduled=False)
            event_obj.save()

            self._repeat(event_obj)

    def _repeat(self, parent_obj):
        children = CalAppModels.Event.objects.filter(parent=parent_obj)
        exceptions = children.filter(exception=True)
        for child in children:
            if not child.exception:
                child.delete()
        event_obj = CalAppModels.Event(event_text=self.info["text"],
                                       begin_datetime=self.info["begin_datetime"],
                                       end_datetime=self.info["end_datetime"],
                                       owner=self.owner,
                                       owner_importance=self.info["owner_importance"],
                                       repetition_type=self.info["repetition_type"],
                                       repetition_number=self.info["repetition_number"],
                                       from_date=self.info["from_date"],
                                       until_date=self.info["until_date"],
                                       exception=False,
                                       parent=parent_obj,
                                       scheduled=False)
        isException = False
        for ex in exceptions:
            if event_obj.begin_datetime == ex.begin_datetime:
                isException = True
        if not isException:
            event_obj.save()
            self.create_shares(event_obj)
        if parent_obj.repetition_type == "weekly":
            daysList = [int(log2(day)) + 1 for day in self.parseWeeklyDays(parent_obj.repetition_number)]

        # Extend into the past
        eventInPast = deepcopy(parent_obj)
        if parent_obj.repetition_type == "weekly":
            eventInPast.begin_datetime -= datetime.timedelta(1)
            eventInPast.end_datetime -= datetime.timedelta(1)
        elif parent_obj.repetition_type == "numdays":
            eventInPast.begin_datetime -= datetime.timedelta(parent_obj.repetition_number)
            eventInPast.end_datetime -= datetime.timedelta(parent_obj.repetition_number)
        else:
            return
        while eventInPast.begin_datetime.date() >= eventInPast.from_date:
            if parent_obj.repetition_type == "weekly":
                dow = eventInPast.begin_datetime.isoweekday() % 7 + 1
                if dow in daysList:
                    newEvent = CalAppModels.Event(event_text=eventInPast.event_text,
                                                  begin_datetime=eventInPast.begin_datetime,
                                                  end_datetime=eventInPast.end_datetime,
                                                  owner=self.owner,
                                                  owner_importance=eventInPast.owner_importance,
                                                  repetition_type=eventInPast.repetition_type,
                                                  repetition_number=eventInPast.repetition_number,
                                                  from_date=eventInPast.from_date,
                                                  until_date=eventInPast.until_date,
                                                  exception=False,
                                                  parent=parent_obj,
                                                  scheduled=False)
                    isException = False
                    for ex in exceptions:
                        if newEvent.begin_datetime == ex.begin_datetime:
                            isException = True
                    if not isException:
                        newEvent.save()
                        self.create_shares(newEvent)
                eventInPast.begin_datetime -= datetime.timedelta(1)
                eventInPast.end_datetime -= datetime.timedelta(1)
            elif parent_obj.repetition_type == "numdays":
                newEvent = CalAppModels.Event(event_text=eventInPast.event_text,
                                              begin_datetime=eventInPast.begin_datetime,
                                              end_datetime=eventInPast.end_datetime,
                                              owner=self.owner,
                                              owner_importance=eventInPast.owner_importance,
                                              repetition_type=eventInPast.repetition_type,
                                              repetition_number=eventInPast.repetition_number,
                                              from_date=eventInPast.from_date,
                                              until_date=eventInPast.until_date,
                                              exception=False,
                                              parent=parent_obj,
                                              scheduled=False)
                isException = False
                for ex in exceptions:
                    if newEvent.begin_datetime == ex.begin_datetime:
                        isException = True
                if not isException:
                    newEvent.save()
                    self.create_shares(newEvent)
                eventInPast.begin_datetime -= datetime.timedelta(parent_obj.repetition_number)
                eventInPast.end_datetime -= datetime.timedelta(parent_obj.repetition_number)

        # Extend into the future
        eventInFuture = deepcopy(parent_obj)
        if parent_obj.repetition_type == "weekly":
            eventInFuture.begin_datetime += datetime.timedelta(1)
            eventInFuture.end_datetime += datetime.timedelta(1)
        elif parent_obj.repetition_type == "numdays":
            eventInFuture.begin_datetime += datetime.timedelta(parent_obj.repetition_number)
            eventInFuture.end_datetime += datetime.timedelta(parent_obj.repetition_number)
        while eventInFuture.begin_datetime.date() <= eventInFuture.until_date:
            if parent_obj.repetition_type == "weekly":
                dow = eventInFuture.begin_datetime.isoweekday() % 7 + 1
                print(eventInFuture.event_text)
                print(eventInFuture.begin_datetime.date())
                print(daysList)
                print(dow)
                if dow in daysList:
                    newEvent = CalAppModels.Event(event_text=eventInFuture.event_text,
                                                  begin_datetime=eventInFuture.begin_datetime,
                                                  end_datetime=eventInFuture.end_datetime,
                                                  owner=self.owner,
                                                  owner_importance=eventInFuture.owner_importance,
                                                  repetition_type=eventInFuture.repetition_type,
                                                  repetition_number=eventInFuture.repetition_number,
                                                  from_date=eventInFuture.from_date,
                                                  until_date=eventInFuture.until_date,
                                                  exception=False,
                                                  parent=parent_obj,
                                                  scheduled=False)
                    isException = False
                    for ex in exceptions:
                        if newEvent.begin_datetime == ex.begin_datetime:
                            isException = True
                    if not isException:
                        newEvent.save()
                        self.create_shares(newEvent)
                eventInFuture.begin_datetime += datetime.timedelta(1)
                eventInFuture.end_datetime += datetime.timedelta(1)
            elif parent_obj.repetition_type == "numdays":
                newEvent = CalAppModels.Event(event_text=eventInFuture.event_text,
                                              begin_datetime=eventInFuture.begin_datetime,
                                              end_datetime=eventInFuture.end_datetime,
                                              owner=self.owner,
                                              owner_importance=eventInFuture.owner_importance,
                                              repetition_type=eventInFuture.repetition_type,
                                              repetition_number=eventInFuture.repetition_number,
                                              from_date=eventInFuture.from_date,
                                              until_date=eventInFuture.until_date,
                                              exception=False,
                                              parent=parent_obj,
                                              scheduled=False)
                isException = False
                for ex in exceptions:
                    if newEvent.begin_datetime == ex.begin_datetime:
                        isException = True
                if not isException:
                    newEvent.save()
                    self.create_shares(newEvent)
                eventInFuture.begin_datetime += datetime.timedelta(parent_obj.repetition_number)
                eventInFuture.end_datetime += datetime.timedelta(parent_obj.repetition_number)


class Task(CalendarItem):
    def parseWeeklyDays(self, num):
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

    def create_shares(self, task_obj):
        if self.info["shares"]:
            for share in self.info["shares"]:
                saved_shares = CalAppModels.User_Task.objects.filter(task=task_obj)
                if len(saved_shares) == 0:
                    user_task_obj = CalAppModels.User_Task(task=task_obj,
                                                           user=share,
                                                           importance=task_obj.owner_importance,
                                                           status="invited")
                    user_task_obj.save()
        saved_shares = CalAppModels.User_Task.objects.filter(task=task_obj)
        for saved_share in saved_shares:
            if saved_share.user not in self.info["shares"]:
                saved_share.delete()

    def save(self, pk=None):
        if pk:
            task_obj = CalAppModels.Task.objects.get(pk=pk)
            task_obj.task_text = self.info["text"]
            task_obj.owner_importance = self.info["owner_importance"]
            task_obj.repetition_type = self.info["repetition_type"]
            task_obj.repetition_number = self.info["repetition_number"]
            task_obj.from_date = self.info["from_date"]
            task_obj.until_date = self.info["until_date"]
            task_obj.due_date = self.info["due_datetime"]
            task_obj.available_date = self.info["available_datetime"]
            task_obj.expected_minutes = self.info["expected_minutes"]
            if task_obj.parent:
                task_obj.exception = True  # Because the child was changed independently of the parent
                temp = self.info["repetition_type"]
                self.info["repetition_type"] = "none"
                self.info["exception_child"] = task_obj
                Task(self.info, self.owner).save()
                self.info["exception_child"] = None
                self.info["repetition_type"] = temp
            task_obj.save()

            if not task_obj.parent:
                self._repeat(task_obj)
        else:
            task_obj = CalAppModels.Task(task_text=self.info["text"],
                                         owner=self.owner,
                                         owner_importance=self.info["owner_importance"],
                                         repetition_type=self.info["repetition_type"],
                                         repetition_number=self.info["repetition_number"],
                                         from_date=self.info["from_date"],
                                         until_date=self.info["until_date"],
                                         exception=False,
                                         scheduled=False,
                                         due_date=self.info["due_datetime"],
                                         available_date=self.info["available_datetime"],
                                         expected_minutes=self.info["expected_minutes"])
            task_obj.save()

            self._repeat(task_obj)

    def _repeat(self, parent_obj):
        children = CalAppModels.Task.objects.filter(parent=parent_obj)
        exceptions = children.filter(exception=True)
        for child in children:
            if not child.exception:
                child.delete()
        task_obj = CalAppModels.Task(task_text=self.info["text"],
                                     owner=self.owner,
                                     owner_importance=self.info["owner_importance"],
                                     repetition_type=self.info["repetition_type"],
                                     repetition_number=self.info["repetition_number"],
                                     from_date=self.info["from_date"],
                                     until_date=self.info["until_date"],
                                     exception=False,
                                     scheduled=False,
                                     due_date=self.info["due_datetime"],
                                     available_date=self.info["available_datetime"],
                                     expected_minutes=self.info["expected_minutes"],
                                     parent=parent_obj)
        isException = False
        for ex in exceptions:
            if task_obj.available_date == ex.available_date:
                isException = True
        if not isException:
            task_obj.save()
            self.create_shares(task_obj)
        if parent_obj.repetition_type == "weekly":
            daysList = [int(log2(day)) + 1 for day in self.parseWeeklyDays(parent_obj.repetition_number)]

        # Extend into the past
        taskInPast = deepcopy(parent_obj)
        if parent_obj.repetition_type == "weekly":
            taskInPast.available_date -= datetime.timedelta(1)
            taskInPast.due_date -= datetime.timedelta(1)
        elif parent_obj.repetition_type == "numdays":
            taskInPast.available_date -= datetime.timedelta(parent_obj.repetition_number)
            taskInPast.due_date -= datetime.timedelta(parent_obj.repetition_number)
        else:
            return
        while taskInPast.available_date.date() >= taskInPast.from_date:
            if parent_obj.repetition_type == "weekly":
                dow = taskInPast.available_date.isoweekday() % 7 + 1
                if dow in daysList:
                    newTask = CalAppModels.Task(task_text=taskInPast.task_text,
                                                owner=self.owner,
                                                owner_importance=taskInPast.owner_importance,
                                                repetition_type=taskInPast.repetition_type,
                                                repetition_number=taskInPast.repetition_number,
                                                from_date=taskInPast.from_date,
                                                until_date=taskInPast.until_date,
                                                exception=False,
                                                parent=parent_obj,
                                                scheduled=False,
                                                due_date=taskInPast.due_date,
                                                available_date=taskInPast.available_date,
                                                expected_minutes=taskInPast.expected_minutes)
                    isException = False
                    for ex in exceptions:
                        if newTask.available_date == ex.available_date:
                            isException = True
                    if not isException:
                        newTask.save()
                        self.create_shares(newTask)
                taskInPast.available_date -= datetime.timedelta(1)
                taskInPast.due_date -= datetime.timedelta(1)
            elif parent_obj.repetition_type == "numdays":
                newTask = CalAppModels.Task(task_text=taskInPast.task_text,
                                            owner=self.owner,
                                            owner_importance=taskInPast.owner_importance,
                                            repetition_type=taskInPast.repetition_type,
                                            repetition_number=taskInPast.repetition_number,
                                            from_date=taskInPast.from_date,
                                            until_date=taskInPast.until_date,
                                            exception=False,
                                            parent=parent_obj,
                                            scheduled=False,
                                            due_date=taskInPast.due_date,
                                            available_date=taskInPast.available_date,
                                            expected_minutes=taskInPast.expected_minutes)
                isException = False
                for ex in exceptions:
                    if newTask.available_date == ex.available_date:
                        isException = True
                if not isException:
                    newTask.save()
                    self.create_shares(newTask)
                taskInPast.available_date -= datetime.timedelta(parent_obj.repetition_number)
                taskInPast.due_date -= datetime.timedelta(parent_obj.repetition_number)

        # Extend into the future
        taskInFuture = deepcopy(parent_obj)
        if parent_obj.repetition_type == "weekly":
            taskInFuture.available_date += datetime.timedelta(1)
            taskInFuture.due_date += datetime.timedelta(1)
        elif parent_obj.repetition_type == "numdays":
            taskInFuture.available_date += datetime.timedelta(parent_obj.repetition_number)
            taskInFuture.due_date += datetime.timedelta(parent_obj.repetition_number)
        while taskInFuture.available_date.date() <= taskInFuture.until_date:
            if parent_obj.repetition_type == "weekly":
                dow = taskInFuture.available_date.isoweekday() % 7 + 1
                if dow in daysList:
                    newTask = CalAppModels.Task(task_text=taskInFuture.task_text,
                                                owner=self.owner,
                                                owner_importance=taskInFuture.owner_importance,
                                                repetition_type=taskInFuture.repetition_type,
                                                repetition_number=taskInFuture.repetition_number,
                                                from_date=taskInFuture.from_date,
                                                until_date=taskInFuture.until_date,
                                                exception=False,
                                                parent=parent_obj,
                                                scheduled=False,
                                                due_date=taskInFuture.due_date,
                                                available_date=taskInFuture.available_date,
                                                expected_minutes=taskInFuture.expected_minutes)
                    isException = False
                    for ex in exceptions:
                        if newTask.available_date == ex.available_date:
                            isException = True
                    if not isException:
                        newTask.save()
                        self.create_shares(newTask)
                taskInFuture.available_date += datetime.timedelta(1)
                taskInFuture.due_date += datetime.timedelta(1)
            elif parent_obj.repetition_type == "numdays":
                newTask = CalAppModels.Task(task_text=taskInFuture.task_text,
                                            owner=self.owner,
                                            owner_importance=taskInFuture.owner_importance,
                                            repetition_type=taskInFuture.repetition_type,
                                            repetition_number=taskInFuture.repetition_number,
                                            from_date=taskInFuture.from_date,
                                            until_date=taskInFuture.until_date,
                                            exception=False,
                                            parent=parent_obj,
                                            scheduled=False,
                                            due_date=taskInFuture.due_date,
                                            available_date=taskInFuture.available_date,
                                            expected_minutes=taskInFuture.expected_minutes)
                isException = False
                for ex in exceptions:
                    if newTask.available_date == ex.available_date:
                        isException = True
                if not isException:
                    newTask.save()
                    self.create_shares(newTask)
                taskInFuture.available_date += datetime.timedelta(parent_obj.repetition_number)
                taskInFuture.due_date += datetime.timedelta(parent_obj.repetition_number)
