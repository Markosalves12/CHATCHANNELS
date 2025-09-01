# chat/forms.py
from django import forms
from django.contrib.auth.models import User
from .models import ChatRoom


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

    def clean_name(self):
        name = self.cleaned_data['name']
        # Se o formulário tiver uma instância (ou seja, é uma edição)
        # verifica se o nome já existe em outra sala
        if self.instance and self.instance.name == name:
            return name

        # Para criação ou mudança de nome em edição
        if ChatRoom.objects.filter(name=name).exists():
            raise forms.ValidationError('Já existe uma sala com este nome')
        return name

    def save(self, commit=True):
        # O commit=False é crucial para que possamos modificar a instância antes de salvá-la
        instance = super().save(commit=False)

        # Obter a lista de participantes do formulário
        participants = self.cleaned_data.get('participants', [])

        # Para edição de uma sala existente
        if self.instance and self.instance.pk:
            current_members = set(self.instance.members.all())

            # Se a sala for privada, o criador sempre deve estar na lista de membros
            if instance.is_private:
                new_members = set(participants)
                new_members.add(self.request.user)
            else:
                # Salas públicas não têm membros adicionados pelo usuário
                new_members = set()

            added_users = new_members - current_members
            removed_users = current_members - new_members

            if commit:
                instance.save()

                # Adicionar novos membros
                for user in added_users:
                    # 'added_by' agora é o usuário logado
                    instance.add_member(user, added_by=self.request.user)

                # Remover membros
                for user in removed_users:
                    instance.remove_member(user)

        # Para criação de uma nova sala
        elif commit:
            instance.created_by = self.request.user
            instance.save()

            if instance.is_private:
                # Adiciona o criador primeiro, como na sua view
                instance.add_member(self.request.user, added_by=self.request.user)

                # Adiciona os outros participantes
                for user in participants:
                    instance.add_member(user, added_by=self.request.user)

        return instance