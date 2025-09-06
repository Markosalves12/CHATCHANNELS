from empresasecundario.utils import define_empresas

def create_global_parameters(request):
    request.session['application'] = 'ZeladorX'
    application = request.session.get('application', '')

    return {
        'application': application
    }

def define_wallet(request):
    try:
        empresas = define_empresas(request=request, userid=request.user.id_random)
    except:
        empresas = {
            'empresas_primarias_ids': 0,
            'em_parceria': '',
        }
    em_parceria = empresas['em_parceria']

    return {
        'em_parceria': em_parceria
    }