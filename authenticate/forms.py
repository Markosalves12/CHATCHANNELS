from django import forms

class LoginForms(forms.Form):
    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    email = forms.EmailField(
        label="Email de usuário",
        required=True,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "example@email.com.br"
            }
        )
    )

    senha = forms.CharField(
        label="Senha",
        required=True,
        max_length=70,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Sua senha"
            }
        )
    )

class EmailReset(forms.Form):
    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    email = forms.EmailField(
        label="Email de usuário",
        required=True,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "example@email.com.br"
            }
        )
    )


class UpdatePassword(forms.Form):
    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    email = forms.EmailField(
        label="Email de usuário",
        required=True,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "example@email.com.br"
            }
        )
    )

    new_password = forms.CharField(
        label="Nova senha",
        required=True,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Digite sua nova senha"
            }
        )
    )

    confirm_password = forms.CharField(
        label="Confirme a nova senha",
        required=True,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Confirme sua nova senha"
            }
        )
    )

    token = forms.CharField(
        label="Token de validação",
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
            }
        )
    )

