from django.db import models
from django.conf import settings
from django.contrib.auth.models import User


class Event(models.Model):
    event_text = models.CharField(max_length=settings.CALENDAR_ITEM_MAX_TEXT_LENGTH)
    begin_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    owner = models.ForeignKey(User, on_delete=models.PROTECT)
    owner_importance = models.IntegerField()


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