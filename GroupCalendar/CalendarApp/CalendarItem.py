from . import models as CalAppModels
from django.utils import timezone


class CalendarItem:
    def __init__(self, info, user):
        self.info = info
        self.owner = user


class Event(CalendarItem):
    def save(self, pk=None):
        if pk:
            event_obj = CalAppModels.Event.objects.get(pk=pk)
            event_obj.event_text = self.info["text"]
            event_obj.begin_datetime = self.info["begin_datetime"]
            event_obj.end_datetime = self.info["end_datetime"]
            event_obj.owner_importance = self.info["owner_importance"]
        else:
            event_obj = CalAppModels.Event(event_text=self.info["text"],
                                           begin_datetime=self.info["begin_datetime"],
                                           end_datetime=self.info["end_datetime"],
                                           owner=self.owner,
                                           owner_importance=self.info["owner_importance"])

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


class Task(CalendarItem):
    def save(self):
        task_obj = CalAppModels.Task(task_text=self.info["text"],
                                     due_date=self.info["due_datetime"],
                                     available_date=self.info["available_datetime"],
                                     owner=self.owner,
                                     owner_importance=self.info["owner_importance"])
        task_obj.save()
        if self.info["shares"]:
            for share in self.info["shares"]:
                user_task_obj = CalAppModels.User_Task(task=task_obj,
                                                       user=share,
                                                       importance=0,
                                                       status="invited")
                user_task_obj.save()
