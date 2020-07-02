from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
import datetime
from django.utils.timezone import make_aware


class Event(models.Model):
    event_text = models.CharField(max_length=settings.CALENDAR_ITEM_MAX_TEXT_LENGTH)
    begin_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    owner_importance = models.IntegerField()
    repetition_type = models.CharField(max_length=20)  # numdays, weekly, none
    repetition_number = models.IntegerField()
    from_date = models.DateField(default=datetime.date.today)
    until_date = models.DateField(default=datetime.date.today)
    parent = models.ForeignKey('self', null=True, on_delete=models.CASCADE, related_name='+')
    exception = models.BooleanField()
    exception_child = models.ForeignKey('self', on_delete=models.CASCADE, null=True, related_name='+')
    scheduled = models.BooleanField()


class User_Event(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    importance = models.IntegerField()
    status = models.CharField(max_length=20)


class Task(models.Model):
    task_text = models.CharField(max_length=settings.CALENDAR_ITEM_MAX_TEXT_LENGTH)
    due_date = models.DateTimeField()
    available_date = models.DateTimeField()
    owner = models.ForeignKey(User, on_delete=models.PROTECT)
    owner_importance = models.IntegerField()
    repetition_type = models.CharField(max_length=20)  # numdays, weekly, none
    repetition_number = models.IntegerField()  # 1 - inf. for numdays, 0 - 6 for Sun-Sat
    from_date = models.DateField(default=lambda: make_aware(datetime.datetime.now()))
    until_date = models.DateField(default=lambda: make_aware(datetime.datetime.now()))
    expected_minutes = models.IntegerField()
    begin_datetime = models.DateTimeField(default=lambda: make_aware(datetime.datetime.now()))
    end_datetime = models.DateTimeField(default=lambda: make_aware(datetime.datetime.now()))
    parent = models.ForeignKey('self', null=True, on_delete=models.CASCADE, related_name='+')
    exception = models.BooleanField()
    exception_child = models.ForeignKey('self', on_delete=models.CASCADE, null=True, related_name='+')
    scheduled = models.BooleanField()


class User_Task(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    importance = models.IntegerField()
    status = models.CharField(max_length=20)


class Contact(models.Model):
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    state = models.CharField(max_length=20)

class Cal_Share(models.Model):
    sharer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    sharee = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=20)

class User_To_Schedule(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    num_seconds_allowed = models.IntegerField()