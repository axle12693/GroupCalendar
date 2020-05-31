from . import models as CalAppModels
from django.utils import timezone

class CalendarItem:
    def __init__(self, info, user):
        self.info = self.process_data(info)
        self.owner = user

class Event(CalendarItem):
    def save(self):
        event_obj = CalAppModels.Event(event_text=self.info.text,
                                       begin_datetime=self.info.begin_datetime,
                                       end_datetime=self.info.end_datetime,
                                       owner=self.owner,
                                       owner_importance=self.info.importance)
        event_obj.save()
        if self.info.shares:
            for share in self.info.shares:
                user_event_obj = CalAppModels.User_Event(event=share.event,
                                                         user=share.user,
                                                         importance=0,
                                                         status="invited")
                user_event_obj.save()

class Task(CalendarItem):
    def save(self):
        task_obj = CalAppModels.Task(task_text=self.info.text,
                                     due_date=self.info.due_date,
                                     available_date=self.info.available_date,
                                     owner=self.owner,
                                     owner_importance=self.info.importance)
        task_obj.save()
        if self.info.shares:
            for share in self.info.shares:
                user_task_obj = CalAppModels.User_Task(task=share.task,
                                                       user=share.user,
                                                       importance=0,
                                                       status="invited")
                user_task_obj.save()