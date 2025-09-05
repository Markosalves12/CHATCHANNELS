from empresasecundario.models import EmpresaSecundaria
from django import forms
from empresasecundario.utils import define_empresas
from zeladorx.models import TypeZeladoria
from empresaprimaria.models import EmpresaPrimaria

class EmpresaSecundariaForms(forms.ModelForm):
    def __init__(self, *args, request, userid=str, type = 'creat/edit', **kwargs):
        super(EmpresaSecundariaForms, self).__init__(*args, **kwargs)
        # Excluir serviços com status 'Desmobilizado' do queryset
        empresas = define_empresas(request=request, userid=userid)
        empresas_primarias_ids = empresas['empresas_primarias_ids']
        setores = empresas['setores']['setores_primaria']

        if setores.exists():
            self.fields['setor'].queryset = self.fields['setor'].queryset.filter(
                id__in=setores
            )
        else:
            self.fields.pop('setor')

        if userid and type=='creat/edit':
            # Ajustar o queryset do campo 'empresaprimaria'
            # self.fields['empresaprimaria'].queryset = self.fields['empresaprimaria'].queryset.filter(
            #     id_random__in=empresas_primarias_ids,
            #     status__in=['Mobilizado']
            # ).distinct()

            self.fields['empresaprimaria'] = forms.ModelChoiceField(
                queryset=EmpresaPrimaria.objects.filter(
                    id_random__in=empresas_primarias_ids,
                    status__in=['Mobilizado']
                ).distinct(),
                widget=forms.Select(
                    attrs={
                        'class': 'form-control',
                    }
                ),
                label='Empresa operadora',
                required=True  # ou False, conforme sua lógica
            )

        if type == 'search':
            for field_name, field in self.fields.items():
                field.required = False

            # self.fields['empresaprimaria'].queryset = self.fields['empresaprimaria'].queryset.filter(
            #     id_random__in=empresas_primarias_ids,
            # ).distinct()

            self.fields['servico_agendado'] = forms.ModelChoiceField(
                queryset=EmpresaPrimaria.objects.filter(
                    id_random__in=empresas_primarias_ids,
                ).distinct(),
                widget=forms.Select(
                    attrs={
                        'class': 'form-control',
                        'style': (
                            'max-height: 40px; overflow-y: auto; max-width: 600px; '
                            'white-space: normal; word-wrap: break-word; overflow-wrap: break-word;'
                        )
                    }
                ),
                label='Empresa operadora',
                required=True  # ou False, conforme sua lógica
            )

    setor = forms.ModelMultipleChoiceField(
        queryset=TypeZeladoria.objects.all(),
        widget=forms.CheckboxSelectMultiple(
            attrs={
                'class': 'checkbox'
            }
        ),
        label='setor',
        required=True  # Defina como True se a seleção de colaboradores for obrigató
    )

    class Meta:
        model = EmpresaSecundaria
        fields = ['nome',
                  # 'razao_social',
                  # 'CNPJ',
                  # 'logo',
                  'setor', 'empresaprimaria', ]
        labels = {
            'nome': 'Nome',
            'setor': 'Setor',
            'empresaprimaria': 'Empresa operadora',
        }

        widgets = {
            'nome': forms.TextInput(
                attrs={
                    'class': 'form-control'
                }
            ),
            'razao_social': forms.TextInput(
                attrs={
                    'class': 'form-control'
                }
            ),
            'CNPJ': forms.TextInput(
                attrs={
                    'class': 'form-control'
                }
            ),
            # 'logo': forms.FileInput(
            #     attrs={
            #         'class': 'form-control'
            #     }
            # ),
            'setor': forms.Select(
                attrs={
                    'class': 'form-control'
                }
            ),
            # 'empresaprimaria': forms.Select(
            #     attrs={
            #         'class': 'form-control'
            #     }
            # )
        }