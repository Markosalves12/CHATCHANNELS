# chat/forms.py
from django import forms
from django.contrib.auth.models import User
from .models import ChatRoom, RoomMembership


class CreateRoomForm(forms.ModelForm):
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        }),
        required=False,
        label='Participantes'
    )

    class Meta:
        model = ChatRoom
        fields = ['name', 'is_private', 'participants']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome da sala',
                'required': True
            }),
            'is_private': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_is_private'
            })
        }
        labels = {
            'name': 'Nome da Sala',
            'is_private': 'Sala Privada'
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.request and self.request.user.is_authenticated:
            self.fields['participants'].queryset = User.objects.exclude(
                id=self.request.user.id
            ).order_by('username')

    def clean_name(self):
        name = self.cleaned_data['name']
        if ChatRoom.objects.filter(name=name).exists():
            raise forms.ValidationError('Já existe uma sala com este nome')
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)

        if commit:
            instance.save()

            # Sempre adicionar o criador como membro em salas privadas
            if instance.is_private:
                # Adicionar o criador da sala como membro
                instance.add_member(self.request.user, added_by=self.request.user)

                # Adicionar participantes selecionados
                participants = self.cleaned_data.get('participants', [])
                for user in participants:
                    # Garantir que o usuário não seja adicionado duas vezes
                    if not instance.members.filter(id=user.id).exists():
                        instance.add_member(user, added_by=self.request.user)

        return instance