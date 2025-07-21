from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class SignUpForm(UserCreationForm):
    email   = forms.EmailField(required=True, label="Email")
    name    = forms.CharField(label="Name", max_length=80)
    surname = forms.CharField(label="Surname", max_length=80, required=False)

    class Meta:
        model  = User
        fields = (
            "email",
            "username",
            "name",
            "surname",
            "password1",
            "password2",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("The email is already in use.")
        return email
    
class ProfileForm(forms.ModelForm):
    class Meta:
        model  = User
        fields = (
            "name",
            "surname",
            "birth_date",
            "city",
            "country",
            "job_title",
            "favourite_club",
            "avatar",
        )
