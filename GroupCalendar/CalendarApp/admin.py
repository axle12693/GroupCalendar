from django.contrib import admin
from CalendarApp.models import Event, Task, User_Task, User_Event, Contact


class EventAdmin(admin.ModelAdmin):
    pass


class TaskAdmin(admin.ModelAdmin):
    pass


class User_TaskAdmin(admin.ModelAdmin):
    pass


class User_EventAdmin(admin.ModelAdmin):
    pass


class ContactAdmin(admin.ModelAdmin):
    pass


admin.site.register(Event, EventAdmin)
admin.site.register(Task, TaskAdmin)
admin.site.register(User_Event, User_EventAdmin)
admin.site.register(User_Task, User_TaskAdmin)
admin.site.register(Contact, ContactAdmin)
