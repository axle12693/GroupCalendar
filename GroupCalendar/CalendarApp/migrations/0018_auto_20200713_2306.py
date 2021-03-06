# Generated by Django 3.0.5 on 2020-07-14 03:06

import CalendarApp.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('CalendarApp', '0017_user_schedule_lock'),
    ]

    operations = [
        migrations.CreateModel(
            name='User_Schedule_Info',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_fast_schedule', models.DateTimeField(default=CalendarApp.models.get_aware_now)),
                ('last_slow_schedule', models.DateTimeField(default=CalendarApp.models.get_aware_now)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.DeleteModel(
            name='User_To_Schedule',
        ),
    ]
