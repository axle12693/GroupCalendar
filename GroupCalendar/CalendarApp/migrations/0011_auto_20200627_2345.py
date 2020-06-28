# Generated by Django 3.0.5 on 2020-06-28 03:45

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('CalendarApp', '0010_auto_20200625_0013'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='scheduled',
            field=models.BooleanField(default=False),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='User_To_Schedule',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('num_seconds_allowed', models.IntegerField()),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
