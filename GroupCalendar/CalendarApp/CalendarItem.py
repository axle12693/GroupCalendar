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

        if self.info["shares"]:
            for share in self.info["shares"]:
                user_event_obj = CalAppModels.User_Event(event=event_obj,
                                                         user=share,
                                                         importance=0,
                                                         status="invited")
                user_event_obj.save()
        if pk:
            saved_shares = CalAppModels.User_Event.objects.filter(event=event_obj)
            for saved_share in saved_shares:
                if saved_share.user not in self.info["shares"]:
                    saved_share.delete()

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
                eventInFuture.begin_datetime += datetime.timedelta(parent_obj.repetition_number)
                eventInFuture.end_datetime += datetime.timedelta(parent_obj.repetition_number)


class Task(CalendarItem):
    def parseNumDays(self, num):
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

    def save(self, pk=None):
        if pk:
            task_obj = CalAppModels.Task.objects.get(pk=pk)
            task_obj.task_text = self.info["text"]
            task_obj.due_datetime = self.info["due_datetime"]
            task_obj.available_datetime = self.info["available_datetime"]
            task_obj.owner_importance = self.info["owner_importance"]
            task_obj.repetition_type = self.info["repetition_type"]
            task_obj.repetition_number = self.info["repetition_number"]
            task_obj.expected_minutes = self.info["expected_minutes"]
            task_obj.from_date = self.info["from_date"]
            task_obj.until_date = self.info["until_date"]
        else:
            task_obj = CalAppModels.Task(task_text=self.info["text"],
                                         due_datetime=self.info["due_datetime"],
                                         available_datetime=self.info["available_datetime"],
                                         owner=self.owner,
                                         owner_importance=self.info["owner_importance"],
                                         repetition_type=self.info["repetition_type"],
                                         repetition_number=self.info["repetition_number"],
                                         expected_minutes=self.info["expected_minutes"],
                                         from_date=self.info["from_date"],
                                         until_date=self.info["until_date"])

        task_obj.save()
        if self.info["shares"]:
            for share in self.info["shares"]:
                user_task_obj = CalAppModels.User_Task(task=task_obj,
                                                       user=share,
                                                       importance=0,
                                                       status="invited")
                user_task_obj.save()
        if pk:
            saved_shares = CalAppModels.User_Task.objects.filter(task=task_obj)
            for saved_share in saved_shares:
                if saved_share.user not in self.info["shares"]:
                    saved_share.delete()

