# Generated by Django 3.0.5 on 2020-06-25 04:13

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('CalendarApp', '0009_auto_20200623_2208'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='exception_child',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='CalendarApp.Event'),
        ),
        migrations.AlterField(
            model_name='event',
            name='parent',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='CalendarApp.Event'),
        ),
    ]
