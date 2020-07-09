# Generated by Django 3.0.5 on 2020-07-07 21:59

import datetime
from django.db import migrations, models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('CalendarApp', '0013_auto_20200707_1600'),
    ]

    operations = [
        migrations.AlterField(
            model_name='task',
            name='begin_datetime',
            field=models.DateTimeField(default=datetime.datetime(2020, 7, 7, 17, 59, 51, 719809, tzinfo=utc)),
        ),
        migrations.AlterField(
            model_name='task',
            name='end_datetime',
            field=models.DateTimeField(default=datetime.datetime(2020, 7, 7, 17, 59, 51, 719809, tzinfo=utc)),
        ),
        migrations.AlterField(
            model_name='task',
            name='from_date',
            field=models.DateField(default=datetime.datetime(2020, 7, 7, 17, 59, 51, 719809, tzinfo=utc)),
        ),
        migrations.AlterField(
            model_name='task',
            name='until_date',
            field=models.DateField(default=datetime.datetime(2020, 7, 7, 17, 59, 51, 719809, tzinfo=utc)),
        ),
    ]