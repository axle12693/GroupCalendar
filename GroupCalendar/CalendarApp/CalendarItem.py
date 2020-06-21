from . import models as CalAppModels
from django.utils import timezone


class CalendarItem:
    def __init__(self, info, user):
        self.info = info
        self.owner = user


class Event(CalendarItem):
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
            event_obj = CalAppModels.Event.objects.get(pk=pk)
            event_obj.event_text = self.info["text"]
            event_obj.begin_datetime = self.info["begin_datetime"]
            event_obj.end_datetime = self.info["end_datetime"]
            event_obj.owner_importance = self.info["owner_importance"]
            event_obj.repetition_type = self.info["repetition_type"]
            event_obj.repetition_number = self.info["repetition_number"]
            event_obj.from_date = self.info["from_date"]
            event_obj.until_date = self.info["until_date"]
        else:
            event_obj = CalAppModels.Event(event_text=self.info["text"],
                                           begin_datetime=self.info["begin_datetime"],
                                           end_datetime=self.info["end_datetime"],
                                           owner=self.owner,
                                           owner_importance=self.info["owner_importance"],
                                           repetition_type=self.info["repetition_type"],
                                           repetition_number=self.info["repetition_number"],
                                           from_date=self.info["from_date"],
                                           until_date=self.info["until_date"])

        event_obj.save()
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

class DisplayEvent:
    def __init__(self, event_obj):
        self.event_text  = event_obj.event_text
        self.begin_datetime = event_obj.begin_datetime
        self.end_datetime = event_obj.end_datetime
        self.owner_importance = event_obj.owner_importance
        self.repetition_type = event_obj.repetition_type
        self.repetition_number = event_obj.repetition_number
        self.from_date = event_obj.from_date
        self.until_date = event_obj.until_date
        self.pk = event_obj.pk

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

