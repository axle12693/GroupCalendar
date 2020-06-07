from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .CalendarItem import Event, Task
from tempus_dominus.widgets import DateTimePicker

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

class AddEventForm(forms.Form):
    def __init__(self, user:User, *args, **kwargs):
        super(AddEventForm, self).__init__(*args, **kwargs)
        allusers = User.objects.all()
        userpk = user.pk
        self.fields["shares"].queryset = allusers.exclude(pk=userpk)

    text = forms.CharField(max_length=256)
    begin_datetime = forms.DateTimeField(widget=DateTimePicker())
    end_datetime = forms.DateTimeField(widget=DateTimePicker())
    owner_importance = forms.IntegerField(max_value=10, min_value=1)
    shares = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple, queryset=User.objects.all(), required=False)

class EditEventForm(forms.Form):
    def __init__(self, user:User, *args, **kwargs):
        super(EditEventForm, self).__init__(*args, **kwargs)
        allusers = User.objects.all()
        userpk = user.pk
        self.fields["shares"].queryset = allusers.exclude(pk=userpk)

    text = forms.CharField(max_length=256)
    begin_datetime = forms.DateTimeField(widget=DateTimePicker())
    end_datetime = forms.DateTimeField(widget=DateTimePicker())
    owner_importance = forms.IntegerField(max_value=10, min_value=1)
    shares = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple, queryset=User.objects.all(), required=False)
    pk = forms.IntegerField(widget=forms.HiddenInput)

class AddTaskForm(forms.Form):
    def __init__(self, user:User, *args, **kwargs):
        super(AddTaskForm, self).__init__(*args, **kwargs)
        allusers = User.objects.all()
        userpk = user.pk
        self.fields["shares"].queryset = allusers.exclude(pk=userpk)

    text = forms.CharField(max_length=256)
    due_datetime = forms.DateTimeField(widget=DateTimePicker())
    available_datetime = forms.DateTimeField(widget=DateTimePicker())
    owner_importance = forms.IntegerField(max_value=10, min_value=1)
    shares = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple, queryset=User.objects.all(), required=False)

class AddContactForm(forms.Form):
    add_contact = forms.CharField(label="Add a contact:")
    pk = forms.IntegerField(widget=forms.HiddenInput)