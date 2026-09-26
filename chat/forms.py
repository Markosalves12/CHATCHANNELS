from django import forms
from django.contrib.auth import get_user_model
from .models import ChatRoom
from empresasecundario.utils import define_empresas

# Usa o modelo de usuário configurado em AUTH_USER_MODEL (no seu caso: gerente.Gerente)
User = get_user_model()


class CreateRoomForm(forms.ModelForm):
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),  # inicia vazio, será preenchido no __init__
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input'
        }),
        required=False,
        label='Participantes'
    )

    class Meta:
        model = ChatRoom
        fields = ['name', 'history_enabled', 'participants']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome da sala',
                'required': True
            }),
            'history_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_history_enabled'
            })
        }
        labels = {
            'name': 'Nome da Sala',
            'history_enabled': 'Permitir histórico de mensagens'
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.request and self.request.user.is_authenticated:
            if not self.request.user.is_admin:
                self.fields['history_enabled'].disabled = True
                self.fields['history_enabled'].help_text = 'Somente administradores podem alterar esta configuração.'

            # 🔹 aplica filtro pelas empresas primárias e status
            empresas = define_empresas(request=self.request, userid=self.request.user.id_random)
            empresas_primarias_ids = empresas['empresas_primarias_ids']

            qs = User.objects.filter(
                empresasecundaria__empresaprimaria__id_random__in=empresas_primarias_ids,
                status='Mobilizado'
            ).exclude(id=self.request.user.id).order_by('username')


            self.fields['participants'].queryset = qs

    def clean_name(self):
        name = self.cleaned_data['name']
        if self.instance and self.instance.pk:
            if self.instance.name == name:
                return name
        if ChatRoom.objects.filter(name=name).exists():
            raise forms.ValidationError('Já existe uma sala com este nome')
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        participants = self.cleaned_data.get('participants', [])
        instance.is_private = True

        # Sala existente → atualização
        if self.instance and self.instance.pk:
            current_members = set(self.instance.members.all())
            new_members = set(participants)
            new_members.add(instance.created_by)

            added_users = new_members - current_members
            removed_users = current_members - new_members

            if commit:
                instance.save()
                for user in added_users:
                    instance.add_member(user, added_by=self.request.user)
                for user in removed_users:
                    instance.remove_member(user)

        # Nova sala → criação
        elif commit:
            instance.created_by = self.request.user
            instance.save()

            instance.add_member(self.request.user, added_by=self.request.user)
            for user in participants:
                instance.add_member(user, added_by=self.request.user)

        return instance
