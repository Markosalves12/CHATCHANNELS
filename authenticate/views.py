# chat/views.py
from django.views.decorators.csrf import csrf_protect
from django.shortcuts import render, redirect
from authenticate.forms import LoginForms, EmailReset, UpdatePassword
from gerente.models import Gerente
from django.contrib import messages
from notifications.utils import enviar_notificacao
from django.utils.crypto import get_random_string
from django.utils.timezone import now
from datetime import timedelta, datetime
from django.contrib.auth import authenticate, login, logout



@csrf_protect
def login_view(request):
    context = {}

    user = request.user
    if user.is_authenticated:
        return redirect('chat_home')

    if request.POST:
        form = LoginForms(request.POST)
        if form.is_valid():
            email = request.POST['email']
            password = request.POST['senha']
            user = authenticate(email=email, password=password)

            if user:
                login(request, user)
                return redirect('chat_home')

    else:
        form = LoginForms()

    context['login_form'] = form
    return render(
        request,
        'login.html',
        context={
            'form': LoginForms
        }
    )

def logout_view(request):
    """View de logout"""
    logout(request)
    messages.success(request, 'Você foi desconectado com sucesso.')
    return redirect('login')



def reset_password(request):
    forms = EmailReset()
    print("1")
    if request.method == "POST":
        forms = EmailReset(request.POST)
        if forms.is_valid():
            email = forms['email'].value()
            print("2")
            try:
                gerente = Gerente.objects.get(
                    email=email
                )
                print("1")
                # Gera um token de redefinição de senha e um token para a URL
                reset_token = get_random_string(9)  # Token único de 32 caracteres
                url_token = get_random_string(16)  # Token adicional para URL
                token_expiration = now() + timedelta(hours=1)  # Expira em 1 hora

                # Armazena o token de redefinição e o token de URL na sessão
                request.session['reset_token'] = reset_token
                request.session['url_token'] = url_token
                request.session['token_expiration'] = token_expiration.isoformat()
                request.session['email'] = email
                print("2")
                enviar_notificacao(
                    destinatario=[email],
                    assunto="Alteração de senha",
                    contexto={
                        'username': gerente.username,
                        'email': gerente.email,
                        'randon_token': reset_token
                    },
                    template='reset_password_email.html'
                )
                print(3)

                messages.success(request, "Token de troca enviado por email")

                return redirect('update_password', url_token)

            except:
                pass

    return render(
        request=request,
        template_name='send_token.html',
        context={
            'form': forms
        }
    )


def update_password(request, token):
    # Verifica se o token da URL é o mesmo que foi armazenado na sessão
    session_token = request.session.get('reset_token')
    session_token_expiration_str = request.session.get('token_expiration')

    forms = UpdatePassword()

    if request.method == "POST":
        forms = UpdatePassword(request.POST)

        if forms.is_valid():
            email = forms['email'].value()
            token = forms['token'].value()
            new_password = forms['new_password'].value()
            confirm_password = forms['confirm_password'].value()


            # Valida se o token da URL e o token da sessão são os mesmos
            if token != session_token:
                messages.error(request, "Token inválido. Solicite outro.")
                return redirect('reset_password')  # Redireciona para a página de solicitação de token

            # Valida se o token expirou
            if session_token_expiration_str:
                # Converte a string de data de expiração para um objeto datetime
                session_token_expiration = datetime.fromisoformat(session_token_expiration_str)
                if now() > session_token_expiration:
                    messages.error(request, "Token expirado. Solicite outro.")
                    return redirect('reset_password')  # Redireciona para a página de solicitação de token

            try:
                gerente = Gerente.objects.get(
                    email=email
                )

                if new_password != confirm_password:
                    messages.error(request, "Senhas devem ser iguais")


                else:
                    # Atualizar as senhas
                    gerente.set_password(new_password)
                    gerente.reset_token = None  # Invalida o token após o uso
                    gerente.token_expiration = None
                    gerente.save()

                    messages.success(request, "Senhas alterada com sucesso")

                    # Redirecionar para uma página de sucesso
                    return redirect('login')

            except:
                pass


    return render(
        request=request,
        template_name='reset_password.html',
        context={
            'form': forms,
            'token': token
        }
    )
