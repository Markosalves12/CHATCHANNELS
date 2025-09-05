from empresaprimaria.models import EmpresaPrimaria
from empresasecundario.models import EmpresaSecundaria
from zeladorx.models import TypeZeladoria
from gerente.models import Gerente
from unidade.models import Unidade

def define_empresas(request, userid):
    gerente = Gerente.objects.get(id_random=userid)

    # IDs das empresas primárias e secundárias
    empresas_primarias_ids = [
        empresa.empresaprimaria.id_random
        for empresa in gerente.empresasecundaria.all()
    ]

    # Caso o gerente seja superusuário, retorna todas as empresas secundárias associadas à empresa primária
    if gerente.is_superuser:
        empresas_secundarias_ids = [
            empresa.id_random
            for empresa in EmpresaSecundaria.objects.filter(empresaprimaria__id_random__in=empresas_primarias_ids)
        ]
    else:
        empresas_secundarias_ids = [
            empresa.id_random
            for empresa in gerente.empresasecundaria.all()
        ]

    # Setores da empresa primária
    empresa_primaria = EmpresaPrimaria.objects.get(id_random=empresas_primarias_ids[0])
    setores_primaria = empresa_primaria.setor.all()  # Acessando o campo de chave estrangeira
    em_parceria = empresa_primaria.nome

    # Flags para habilitar campos da empresa primária
    habilitar_jardinagem = False
    habilitar_limpeza = False

    # Flags para habilitar campos da empresa secundária
    habilitar_jardinagem_secundaria = False
    habilitar_limpeza_secundaria = False

    # Checar os setores da empresa primária para definir as flags
    for objeto in TypeZeladoria.objects.filter(id__in=setores_primaria):
        if 'Jardinagem' in objeto.setor:
            habilitar_jardinagem = True
            # Definir permissão secundária se is_superuser for True
            if gerente.is_superuser:
                habilitar_jardinagem_secundaria = True

        if 'Limpeza predial' in objeto.setor:
            habilitar_limpeza = True
            # Definir permissão secundária se is_superuser for True
            if gerente.is_superuser:
                habilitar_limpeza_secundaria = True

    # Setores das empresas secundárias e IDs das unidades atendidas
    setores_secundarias = []
    unidades_secundarias_ids = []

    # Buscar todas as unidades que estão associadas às empresas secundárias
    if gerente.is_superuser:
        # Se superusuário, retornar todas as unidades associadas às empresas secundárias
        unidades_secundarias = Unidade.objects.filter(empresasecundaria__id_random__in=empresas_secundarias_ids)
    else:
        # Se não for superusuário, filtrar pelas unidades específicas onde o gerente está alocado
        unidades_secundarias = Unidade.objects.filter(
            empresasecundaria__id_random__in=empresas_secundarias_ids,
        )

    unidades_secundarias_ids.extend([unidade.id_random for unidade in unidades_secundarias])

    # Verificar os setores das empresas secundárias
    for empresa_secundaria in EmpresaSecundaria.objects.filter(id_random__in=empresas_secundarias_ids):
        setores = empresa_secundaria.setor.all()
        setores_secundarias.extend(setores)

        # Verificar se algum setor da empresa secundária é jardinagem ou limpeza
        for objeto in TypeZeladoria.objects.filter(id__in=setores):
            if 'Jardinagem' in objeto.setor:
                habilitar_jardinagem_secundaria = True
            if 'Limpeza predial' in objeto.setor:
                habilitar_limpeza_secundaria = True

    # Retornar as informações das empresas, setores e unidades
    return {
        'empresas_primarias_ids': empresas_primarias_ids,
        'empresas_secundarias_ids': empresas_secundarias_ids,
        'em_parceria': em_parceria,
        'setores': {
            'habilitar_jardinagem': habilitar_jardinagem,
            'habilitar_limpeza': habilitar_limpeza,
            'habilitar_jardinagem_secundaria': habilitar_jardinagem_secundaria,
            'habilitar_limpeza_secundaria': habilitar_limpeza_secundaria,
            'setores_primaria': setores_primaria,
            'setores_secundarias': setores_secundarias,
        },
        'unidades_secundarias_ids': unidades_secundarias_ids
    }
