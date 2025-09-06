from gerente.models import Gerente


def define_empresas(request, userid):
    # Busca o gerente e prefetch apenas da empresa secundária -> primária
    gerente = Gerente.objects.prefetch_related(
        'empresasecundaria__empresaprimaria'
    ).only('id_random').get(id_random=userid)

    # IDs das empresas primárias distintas
    empresas_primarias_ids = list(
        gerente.empresasecundaria.values_list('empresaprimaria__id_random', flat=True).distinct()
    )

    if not empresas_primarias_ids:
        return {
            'empresas_primarias_ids': [],
            'em_parceria': ''
        }

    # Nome da primeira empresa primária (já carregada no prefetch)
    primeira_empresaprimaria = gerente.empresasecundaria.first().empresaprimaria
    em_parceria = primeira_empresaprimaria.nome if primeira_empresaprimaria else ''

    return {
        'empresas_primarias_ids': empresas_primarias_ids,
        'em_parceria': em_parceria
    }
