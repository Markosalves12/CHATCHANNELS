# chat/views.py
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect
from authenticate.forms import LoginForms


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


# @csrf_protect
# def login_view(request):
#     """View de login personalizada"""
#     if request.user.is_authenticated:
#         return redirect('chat_home')
#
#     if request.method == 'POST':
#         form = AuthenticationForm(request, data=request.POST)
#         if form.is_valid():
#             username = form.cleaned_data.get('username')
#             password = form.cleaned_data.get('password')
#             user = authenticate(username=username, password=password)
#
#             if user is not None:
#                 login(request, user)
#                 messages.success(request, f'Bem-vindo de volta, {username}!')
#
#                 # Redirecionar para a próxima página ou home
#                 next_page = request.GET.get('next', 'chat_home')
#                 return redirect(next_page)
#             else:
#                 messages.error(request, 'Credenciais inválidas.')
#         else:
#             messages.error(request, 'Por favor, corrija os erros abaixo.')
#             print("########")
#             print(request)
#             print("########")
#     else:
#         form = AuthenticationForm()
#
#     return render(request, 'login.html', {'form': form})
#

def logout_view(request):
    """View de logout"""
    logout(request)
    messages.success(request, 'Você foi desconectado com sucesso.')
    return redirect('login')
