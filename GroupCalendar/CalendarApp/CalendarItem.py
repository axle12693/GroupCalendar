from . import models as cal_app_models
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
                user_event_obj = cal_app_models.User_Event(event=event_obj,
                                                           user=share,
                                                           importance=event_obj.owner_importance,
                                                           status="invited")
                user_event_obj.save()
        saved_shares = cal_app_models.User_Event.objects.filter(event=event_obj)
        for saved_share in saved_shares:
            if saved_share.user not in self.info["shares"]:
                saved_share.delete()

    def save(self, pk=None):
        if pk:
            event_obj = cal_app_models.Event.objects.get(pk=pk)
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
            event_obj = cal_app_models.Event(event_text=self.info["text"],
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
        children = cal_app_models.Event.objects.filter(parent=parent_obj)
        exceptions = children.filter(exception=True)
        for child in children:
            if not child.exception:
                child.delete()
        event_obj = cal_app_models.Event(event_text=self.info["text"],
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
        is_exception = False
        for ex in exceptions:
            if event_obj.begin_datetime == ex.begin_datetime:
                is_exception = True
        if not is_exception:
            event_obj.save()
            self.create_shares(event_obj)
        if parent_obj.repetition_type == "weekly":
            days_list = [int(log2(day)) + 1 for day in self.parseWeeklyDays(parent_obj.repetition_number)]

        # Extend into the past
        event_in_past = deepcopy(parent_obj)
        if parent_obj.repetition_type == "weekly":
            event_in_past.begin_datetime -= datetime.timedelta(1)
            event_in_past.end_datetime -= datetime.timedelta(1)
        elif parent_obj.repetition_type == "numdays":
            event_in_past.begin_datetime -= datetime.timedelta(parent_obj.repetition_number)
            event_in_past.end_datetime -= datetime.timedelta(parent_obj.repetition_number)
        else:
            return
        while event_in_past.begin_datetime.date() >= event_in_past.from_date:
            if parent_obj.repetition_type == "weekly":
                dow = event_in_past.begin_datetime.isoweekday() % 7 + 1
                if dow in days_list and event_in_past.begin_datetime.date() <= event_in_past.until_date:
                    new_event = cal_app_models.Event(event_text=event_in_past.event_text,
                                                    begin_datetime=event_in_past.begin_datetime,
                                                    end_datetime=event_in_past.end_datetime,
                                                    owner=self.owner,
                                                    owner_importance=event_in_past.owner_importance,
                                                    repetition_type=event_in_past.repetition_type,
                                                    repetition_number=event_in_past.repetition_number,
                                                    from_date=event_in_past.from_date,
                                                    until_date=event_in_past.until_date,
                                                    exception=False,
                                                    parent=parent_obj,
                                                    scheduled=False)
                    is_exception = False
                    for ex in exceptions:
                        if new_event.begin_datetime == ex.begin_datetime:
                            is_exception = True
                    if not is_exception:
                        new_event.save()
                        self.create_shares(new_event)
                event_in_past.begin_datetime -= datetime.timedelta(1)
                event_in_past.end_datetime -= datetime.timedelta(1)
            elif parent_obj.repetition_type == "numdays":
                if event_in_past.begin_datetime.date() <= event_in_past.until_date:
                    new_event = cal_app_models.Event(event_text=event_in_past.event_text,
                                                    begin_datetime=event_in_past.begin_datetime,
                                                    end_datetime=event_in_past.end_datetime,
                                                    owner=self.owner,
                                                    owner_importance=event_in_past.owner_importance,
                                                    repetition_type=event_in_past.repetition_type,
                                                    repetition_number=event_in_past.repetition_number,
                                                    from_date=event_in_past.from_date,
                                                    until_date=event_in_past.until_date,
                                                    exception=False,
                                                    parent=parent_obj,
                                                    scheduled=False)
                    is_exception = False
                    for ex in exceptions:
                        if new_event.begin_datetime == ex.begin_datetime:
                            is_exception = True
                    if not is_exception:
                        new_event.save()
                        self.create_shares(new_event)
                event_in_past.begin_datetime -= datetime.timedelta(parent_obj.repetition_number)
                event_in_past.end_datetime -= datetime.timedelta(parent_obj.repetition_number)

        # Extend into the future
        event_in_future = deepcopy(parent_obj)
        if parent_obj.repetition_type == "weekly":
            event_in_future.begin_datetime += datetime.timedelta(1)
            event_in_future.end_datetime += datetime.timedelta(1)
        elif parent_obj.repetition_type == "numdays":
            event_in_future.begin_datetime += datetime.timedelta(parent_obj.repetition_number)
            event_in_future.end_datetime += datetime.timedelta(parent_obj.repetition_number)
        while event_in_future.begin_datetime.date() <= event_in_future.until_date:
            if parent_obj.repetition_type == "weekly":
                dow = event_in_future.begin_datetime.isoweekday() % 7 + 1
                print(event_in_future.event_text)
                print(event_in_future.begin_datetime.date())
                print(days_list)
                print(dow)
                if dow in days_list and event_in_future.begin_datetime.date() >= event_in_future.from_date:
                    new_event = cal_app_models.Event(event_text=event_in_future.event_text,
                                                    begin_datetime=event_in_future.begin_datetime,
                                                    end_datetime=event_in_future.end_datetime,
                                                    owner=self.owner,
                                                    owner_importance=event_in_future.owner_importance,
                                                    repetition_type=event_in_future.repetition_type,
                                                    repetition_number=event_in_future.repetition_number,
                                                    from_date=event_in_future.from_date,
                                                    until_date=event_in_future.until_date,
                                                    exception=False,
                                                    parent=parent_obj,
                                                    scheduled=False)
                    is_exception = False
                    for ex in exceptions:
                        if new_event.begin_datetime == ex.begin_datetime:
                            is_exception = True
                    if not is_exception:
                        new_event.save()
                        self.create_shares(new_event)
                event_in_future.begin_datetime += datetime.timedelta(1)
                event_in_future.end_datetime += datetime.timedelta(1)
            elif parent_obj.repetition_type == "numdays":

                if event_in_future.begin_datetime.date() >= event_in_future.from_date:
                    new_event = cal_app_models.Event(event_text=event_in_future.event_text,
                                                    begin_datetime=event_in_future.begin_datetime,
                                                    end_datetime=event_in_future.end_datetime,
                                                    owner=self.owner,
                                                    owner_importance=event_in_future.owner_importance,
                                                    repetition_type=event_in_future.repetition_type,
                                                    repetition_number=event_in_future.repetition_number,
                                                    from_date=event_in_future.from_date,
                                                    until_date=event_in_future.until_date,
                                                    exception=False,
                                                    parent=parent_obj,
                                                    scheduled=False)
                    is_exception = False
                    for ex in exceptions:
                        if new_event.begin_datetime == ex.begin_datetime:
                            is_exception = True
                    if not is_exception:
                        new_event.save()
                        self.create_shares(new_event)
                event_in_future.begin_datetime += datetime.timedelta(parent_obj.repetition_number)
                event_in_future.end_datetime += datetime.timedelta(parent_obj.repetition_number)


class Task(CalendarItem):
    def parse_weekly_days(self, num):
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
                saved_shares = cal_app_models.User_Task.objects.filter(task=task_obj)
                if len(saved_shares) == 0:
                    user_task_obj = cal_app_models.User_Task(task=task_obj,
                                                             user=share,
                                                             importance=task_obj.owner_importance,
                                                             status="invited")
                    user_task_obj.save()
        saved_shares = cal_app_models.User_Task.objects.filter(task=task_obj)
        for saved_share in saved_shares:
            if saved_share.user not in self.info["shares"]:
                saved_share.delete()

    def save(self, pk=None):
        if pk:
            task_obj = cal_app_models.Task.objects.get(pk=pk)
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
            task_obj = cal_app_models.Task(task_text=self.info["text"],
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
        children = cal_app_models.Task.objects.filter(parent=parent_obj)
        exceptions = children.filter(exception=True)
        for child in children:
            if not child.exception:
                child.delete()
        task_obj = cal_app_models.Task(task_text=self.info["text"],
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
        is_exception = False
        for ex in exceptions:
            if task_obj.available_date == ex.available_date:
                is_exception = True
        if not is_exception:
            task_obj.save()
            self.create_shares(task_obj)
        if parent_obj.repetition_type == "weekly":
            days_list = [int(log2(day)) + 1 for day in self.parse_weekly_days(parent_obj.repetition_number)]

        # Extend into the past
        task_in_past = deepcopy(parent_obj)
        if parent_obj.repetition_type == "weekly":
            task_in_past.available_date -= datetime.timedelta(1)
            task_in_past.due_date -= datetime.timedelta(1)
        elif parent_obj.repetition_type == "numdays":
            task_in_past.available_date -= datetime.timedelta(parent_obj.repetition_number)
            task_in_past.due_date -= datetime.timedelta(parent_obj.repetition_number)
        else:
            return
        while task_in_past.available_date.date() >= task_in_past.from_date:
            if parent_obj.repetition_type == "weekly":
                dow = task_in_past.available_date.isoweekday() % 7 + 1
                if dow in days_list and task_in_past.available_date.date() <= task_in_past.until_date:
                    new_task = cal_app_models.Task(task_text=task_in_past.task_text,
                                                  owner=self.owner,
                                                  owner_importance=task_in_past.owner_importance,
                                                  repetition_type=task_in_past.repetition_type,
                                                  repetition_number=task_in_past.repetition_number,
                                                  from_date=task_in_past.from_date,
                                                  until_date=task_in_past.until_date,
                                                  exception=False,
                                                  parent=parent_obj,
                                                  scheduled=False,
                                                  due_date=task_in_past.due_date,
                                                  available_date=task_in_past.available_date,
                                                  expected_minutes=task_in_past.expected_minutes)
                    is_exception = False
                    for ex in exceptions:
                        if new_task.available_date == ex.available_date:
                            is_exception = True
                    if not is_exception:
                        new_task.save()
                        self.create_shares(new_task)
                task_in_past.available_date -= datetime.timedelta(1)
                task_in_past.due_date -= datetime.timedelta(1)
            elif parent_obj.repetition_type == "numdays":
                if task_in_past.available_date.date() <= task_in_past.until_date:
                    new_task = cal_app_models.Task(task_text=task_in_past.task_text,
                                                  owner=self.owner,
                                                  owner_importance=task_in_past.owner_importance,
                                                  repetition_type=task_in_past.repetition_type,
                                                  repetition_number=task_in_past.repetition_number,
                                                  from_date=task_in_past.from_date,
                                                  until_date=task_in_past.until_date,
                                                  exception=False,
                                                  parent=parent_obj,
                                                  scheduled=False,
                                                  due_date=task_in_past.due_date,
                                                  available_date=task_in_past.available_date,
                                                  expected_minutes=task_in_past.expected_minutes)
                    is_exception = False
                    for ex in exceptions:
                        if new_task.available_date == ex.available_date:
                            is_exception = True
                    if not is_exception:
                        new_task.save()
                        self.create_shares(new_task)
                task_in_past.available_date -= datetime.timedelta(parent_obj.repetition_number)
                task_in_past.due_date -= datetime.timedelta(parent_obj.repetition_number)

        # Extend into the future
        task_in_future = deepcopy(parent_obj)
        if parent_obj.repetition_type == "weekly":
            task_in_future.available_date += datetime.timedelta(1)
            task_in_future.due_date += datetime.timedelta(1)
        elif parent_obj.repetition_type == "numdays":
            task_in_future.available_date += datetime.timedelta(parent_obj.repetition_number)
            task_in_future.due_date += datetime.timedelta(parent_obj.repetition_number)
        while task_in_future.available_date.date() <= task_in_future.until_date:
            if parent_obj.repetition_type == "weekly":
                dow = task_in_future.available_date.isoweekday() % 7 + 1
                if dow in days_list and task_in_future.available_date.date() >= task_in_future.from_date:
                    new_task = cal_app_models.Task(task_text=task_in_future.task_text,
                                                  owner=self.owner,
                                                  owner_importance=task_in_future.owner_importance,
                                                  repetition_type=task_in_future.repetition_type,
                                                  repetition_number=task_in_future.repetition_number,
                                                  from_date=task_in_future.from_date,
                                                  until_date=task_in_future.until_date,
                                                  exception=False,
                                                  parent=parent_obj,
                                                  scheduled=False,
                                                  due_date=task_in_future.due_date,
                                                  available_date=task_in_future.available_date,
                                                  expected_minutes=task_in_future.expected_minutes)
                    is_exception = False
                    for ex in exceptions:
                        if new_task.available_date == ex.available_date:
                            is_exception = True
                    if not is_exception:
                        new_task.save()
                        self.create_shares(new_task)
                task_in_future.available_date += datetime.timedelta(1)
                task_in_future.due_date += datetime.timedelta(1)
            elif parent_obj.repetition_type == "numdays":
                if task_in_future.available_date.date() >= task_in_future.from_date:
                    new_task = cal_app_models.Task(task_text=task_in_future.task_text,
                                                  owner=self.owner,
                                                  owner_importance=task_in_future.owner_importance,
                                                  repetition_type=task_in_future.repetition_type,
                                                  repetition_number=task_in_future.repetition_number,
                                                  from_date=task_in_future.from_date,
                                                  until_date=task_in_future.until_date,
                                                  exception=False,
                                                  parent=parent_obj,
                                                  scheduled=False,
                                                  due_date=task_in_future.due_date,
                                                  available_date=task_in_future.available_date,
                                                  expected_minutes=task_in_future.expected_minutes)
                    is_exception = False
                    for ex in exceptions:
                        if new_task.available_date == ex.available_date:
                            is_exception = True
                    if not is_exception:
                        new_task.save()
                        self.create_shares(new_task)
                task_in_future.available_date += datetime.timedelta(parent_obj.repetition_number)
                task_in_future.due_date += datetime.timedelta(parent_obj.repetition_number)
