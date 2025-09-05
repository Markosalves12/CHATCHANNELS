from empresasecundario.utils import define_empresas

def create_global_parameters(request):
    request.session['application'] = 'ZeladorX'
    application = request.session.get('application', '')

    return {
        'application': application
    }

def define_wallet(request):
    try:
        empresas = define_empresas(request=request, userid=request.session.get('userid', ''))
    except:
        empresas = {
            'empresas_primarias_ids': 0,
            'empresas_secundarias_ids': 0,
            'em_parceria': '',
            'setores': {
                'habilitar_jardinagem': False,
                'habilitar_limpeza': False,
                'habilitar_jardinagem_secundaria': False,
                'habilitar_limpeza_secundaria': False,
                'setores_primaria': '',
                'setores_secundarias': '',
            }
        }

    setores = empresas['setores']
    em_parceria = empresas['em_parceria']
    habilitar_jardinagem = False
    habilitar_limpeza = False

    if setores['habilitar_jardinagem_secundaria'] and setores['habilitar_jardinagem']:
        habilitar_jardinagem = True

    if setores['habilitar_limpeza_secundaria'] and setores['habilitar_limpeza']:
        habilitar_limpeza = True

    return {
        'habilitar_jardinagem': habilitar_jardinagem,
        'habilitar_limpeza': habilitar_limpeza,
        'em_parceria': em_parceria
    }