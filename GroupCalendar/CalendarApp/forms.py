from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from tempus_dominus.widgets import DateTimePicker, DatePicker
from . import models as cal_app_models


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
        contact_objects1 = cal_app_models.Contact.objects.filter(user1=user, state="accepted")
        contact_objects2 = cal_app_models.Contact.objects.filter(user2=user, state="accepted")
        contact_set = {c.user2 for c in contact_objects1}.union({c.user1 for c in contact_objects2})
        contact_pks = {con.pk for con in contact_set}
        contacts = User.objects.filter(pk__in=contact_pks)
        self.fields["shares"].queryset = contacts
        self.fields["owner_importance"].help_text += "<br>1 is lowest, 10 is highest"

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
                                            required=False,
                                            label="Include these users:")
    repetition_type = forms.ChoiceField(choices=(("none", "Do not repeat"),
                                                 ("weekly", "Repeat every week on..."),
                                                 ("numdays", "Repeat every n days")),
                                        widget=forms.RadioSelect)
    repetition_number = forms.IntegerField(widget=forms.HiddenInput,
                                           initial=0)
    from_date = forms.DateField(widget=DatePicker(attrs={'autocomplete': 'off'}), label='Start repeating on:')
    until_date = forms.DateField(widget=DatePicker(attrs={'autocomplete': 'off'}), label='Stop repeating on:')


class EditEventForm(forms.Form):
    def __init__(self, user: User, *args, **kwargs):
        super(EditEventForm, self).__init__(*args, **kwargs)
        contact_objects1 = cal_app_models.Contact.objects.filter(user1=user, state="accepted")
        contact_objects2 = cal_app_models.Contact.objects.filter(user2=user, state="accepted")
        contact_set = {c.user2 for c in contact_objects1}.union({c.user1 for c in contact_objects2})
        contact_pks = {con.pk for con in contact_set}
        contacts = User.objects.filter(pk__in=contact_pks)
        self.fields["shares"].queryset = contacts
        self.fields["owner_importance"].help_text += "<br>1 is lowest, 10 is highest"

    text = forms.CharField(max_length=256)
    begin_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    end_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    owner_importance = forms.IntegerField(max_value=10, min_value=1)
    shares = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                            queryset=User.objects.all(),
                                            required=False,
                                            label="Include these users:")
    pk = forms.IntegerField(widget=forms.HiddenInput)
    repetition_type = forms.ChoiceField(choices=(("none", "Do not repeat"),
                                                 ("weekly", "Repeat every week on..."),
                                                 ("numdays", "Repeat every n days")),
                                        widget=forms.RadioSelect)
    repetition_number = forms.IntegerField(widget=forms.HiddenInput,
                                           initial=0)
    from_date = forms.DateField(widget=DatePicker(attrs={'autocomplete': 'off'}), label='Start repeating on:')
    until_date = forms.DateField(widget=DatePicker(attrs={'autocomplete': 'off'}), label='Stop repeating on:')
    all = forms.CharField(widget=forms.HiddenInput, required=False)


class EditSharedEventForm(forms.Form):
    def __init__(self, user: User, *args, **kwargs):
        super(EditSharedEventForm, self).__init__(*args, **kwargs)
        self.fields["importance"].help_text += "<br>1 is lowest, 10 is highest"
    importance = forms.IntegerField(max_value=10, min_value=1)
    pk = forms.IntegerField(widget=forms.HiddenInput)



class AddTaskForm(forms.Form):
    def __init__(self, user: User, *args, **kwargs):
        super(AddTaskForm, self).__init__(*args, **kwargs)
        contactObjects1 = cal_app_models.Contact.objects.filter(user1=user, state="accepted")
        contactObjects2 = cal_app_models.Contact.objects.filter(user2=user, state="accepted")
        contactSet = {c.user2 for c in contactObjects1}.union({c.user1 for c in contactObjects2})
        contactPKs = {con.pk for con in contactSet}
        contacts = User.objects.filter(pk__in=contactPKs)
        self.fields["shares"].queryset = contacts
        self.fields["owner_importance"].help_text += "<br>1 is lowest, 10 is highest"

    text = forms.CharField(max_length=256)
    due_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    available_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    expected_minutes = forms.IntegerField()
    owner_importance = forms.IntegerField(max_value=10, min_value=1)
    shares = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                            queryset=User.objects.all(),
                                            required=False,
                                            label="Include these users:")
    repetition_type = forms.ChoiceField(choices=(("none", "Do not repeat"),
                                                 ("weekly", "Repeat every week on..."),
                                                 ("numdays", "Repeat every n days")),
                                        widget=forms.RadioSelect)
    repetition_number = forms.IntegerField(widget=forms.HiddenInput,
                                           initial=0)
    from_date = forms.DateField(widget=DatePicker(attrs={'autocomplete': 'off'}), label='Start repeating on:')
    until_date = forms.DateField(widget=DatePicker(attrs={'autocomplete': 'off'}), label='Stop repeating on:')


class AddContactForm(forms.Form):
    add_contact = forms.CharField(label="Add a contact:")
    pk = forms.IntegerField(widget=forms.HiddenInput)


class EditTaskForm(forms.Form):
    def __init__(self, user: User, *args, **kwargs):
        super(EditTaskForm, self).__init__(*args, **kwargs)
        contactObjects1 = cal_app_models.Contact.objects.filter(user1=user, state="accepted")
        contactObjects2 = cal_app_models.Contact.objects.filter(user2=user, state="accepted")
        contactSet = {c.user2 for c in contactObjects1}.union({c.user1 for c in contactObjects2})
        contactPKs = {con.pk for con in contactSet}
        contacts = User.objects.filter(pk__in=contactPKs)
        self.fields["shares"].queryset = contacts
        self.fields["owner_importance"].help_text += "<br>1 is lowest, 10 is highest"

    text = forms.CharField(max_length=256)
    due_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    available_datetime = forms.DateTimeField(widget=DateTimePicker(attrs={'autocomplete': 'off'}))
    expected_minutes = forms.IntegerField(label="Expected minutes to complete:")
    owner_importance = forms.IntegerField(max_value=10, min_value=1)
    shares = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                            queryset=User.objects.all(),
                                            required=False,
                                            label="Include these users:")
    pk = forms.IntegerField(widget=forms.HiddenInput)
    repetition_type = forms.ChoiceField(choices=(("none", "Do not repeat"),
                                                 ("weekly", "Repeat every week on..."),
                                                 ("numdays", "Repeat every n days")),
                                        widget=forms.RadioSelect)
    repetition_number = forms.IntegerField(widget=forms.HiddenInput,
                                           initial=0)
    from_date = forms.DateField(widget=DatePicker(attrs={'autocomplete': 'off'}), label='Start repeating on:')
    until_date = forms.DateField(widget=DatePicker(attrs={'autocomplete': 'off'}), label='Stop repeating on:')
    all = forms.CharField(widget=forms.HiddenInput, required=False)


class EditSharedTaskForm(forms.Form):
    def __init__(self, user: User, *args, **kwargs):
        super(EditSharedTaskForm, self).__init__(*args, **kwargs)
        self.fields["importance"].help_text += "<br>1 is lowest, 10 is highest"
    importance = forms.IntegerField(max_value=10, min_value=1)
    pk = forms.IntegerField(widget=forms.HiddenInput)


class RepetitionForm(forms.Form):
    days = forms.MultipleChoiceField(choices=((1, "Sunday"),
                                              (2, "Monday"),
                                              (4, "Tuesday"),
                                              (8, "Wednesday"),
                                              (16, "Thursday"),
                                              (32, "Friday"),
                                              (64, "Saturday")),
                                     widget=forms.CheckboxSelectMultiple)
    number_of_days = forms.IntegerField(initial=0)

