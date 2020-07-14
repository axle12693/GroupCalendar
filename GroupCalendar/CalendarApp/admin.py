from django.contrib import admin
from .models import Event, Task, User_Task, User_Event, Contact, Cal_Share, User_Schedule_Lock


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


class Cal_ShareAdmin(admin.ModelAdmin):
    pass


class User_Schedule_LockAdmin(admin.ModelAdmin):
    pass


admin.site.register(Event, EventAdmin)
admin.site.register(Task, TaskAdmin)
admin.site.register(User_Event, User_EventAdmin)
admin.site.register(User_Task, User_TaskAdmin)
admin.site.register(Contact, ContactAdmin)
admin.site.register(Cal_Share, Cal_ShareAdmin)
admin.site.register(User_Schedule_Lock, User_Schedule_LockAdmin)
