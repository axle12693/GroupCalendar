from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .CalendarItem import Event, Task
from tempus_dominus.widgets import DateTimePicker
from . import models as CalAppModels


class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()

    def __init__(self, *args, **kwargs):
        super(UserRegisterForm, self).__init__(*args, **kwargs)
        self.fields["username"].help_text += "<br>This is how people will find you!"

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class AddEventForm(forms.Form):
    def __init__(self, user: User, *args, **kwargs):
        super(AddEventForm, self).__init__(*args, **kwargs)
        contactObjects1 = CalAppModels.Contact.objects.filter(user1=user, state="accepted")
        contactObjects2 = CalAppModels.Contact.objects.filter(user2=user, state="accepted")
        contactSet = {c.user2 for c in contactObjects1}.union({c.user1 for c in contactObjects2})
        contactPKs = {con.pk for con in contactSet}
        contacts = User.objects.filter(pk__in=contactPKs)
        self.fields["shares"].queryset = contacts

    def clean(self):
        cd = super(AddEventForm, self).clean()
        if self.cleaned_data["begin_datetime"] >= self.cleaned_data["end_datetime"]:
            err = forms.ValidationError("End must be after beginning!", code="invalid_date")
            self.add_error("end_datetime", err)
        return cd

    text = forms.CharField(max_length=256)
    begin_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    end_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    owner_importance = forms.IntegerField(max_value=10, min_value=1)
    shares = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                            queryset=User.objects.all(),
                                            required=False)


class EditEventForm(forms.Form):
    def __init__(self, user: User, *args, **kwargs):
        super(EditEventForm, self).__init__(*args, **kwargs)
        contactObjects1 = CalAppModels.Contact.objects.filter(user1=user, state="accepted")
        contactObjects2 = CalAppModels.Contact.objects.filter(user2=user, state="accepted")
        contactSet = {c.user2 for c in contactObjects1}.union({c.user1 for c in contactObjects2})
        contactPKs = {con.pk for con in contactSet}
        contacts = User.objects.filter(pk__in=contactPKs)
        self.fields["shares"].queryset = contacts

    text = forms.CharField(max_length=256)
    begin_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    end_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    owner_importance = forms.IntegerField(max_value=10, min_value=1)
    shares = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                            queryset=User.objects.all(),
                                            required=False)
    pk = forms.IntegerField(widget=forms.HiddenInput)


class EditSharedEventForm(forms.Form):
    importance = forms.IntegerField(max_value=10, min_value=1)
    pk = forms.IntegerField(widget=forms.HiddenInput)


class AddTaskForm(forms.Form):
    def __init__(self, user: User, *args, **kwargs):
        super(AddTaskForm, self).__init__(*args, **kwargs)
        contactObjects1 = CalAppModels.Contact.objects.filter(user1=user, state="accepted")
        contactObjects2 = CalAppModels.Contact.objects.filter(user2=user, state="accepted")
        contactSet = {c.user2 for c in contactObjects1}.union({c.user1 for c in contactObjects2})
        contactPKs = {con.pk for con in contactSet}
        contacts = User.objects.filter(pk__in=contactPKs)
        self.fields["shares"].queryset = contacts

    text = forms.CharField(max_length=256)
    due_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    available_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    owner_importance = forms.IntegerField(max_value=10, min_value=1)
    shares = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                            queryset=User.objects.all(),
                                            required=False)


class AddContactForm(forms.Form):
    add_contact = forms.CharField(label="Add a contact:")
    pk = forms.IntegerField(widget=forms.HiddenInput)
