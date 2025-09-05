from django.core.mail import EmailMessage, send_mail
from setup.settings import EMAIL_HOST_USER
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def enviar_notificacao(destinatario, assunto, contexto, template):
    html_content = render_to_string(
        template_name=template,
        context=contexto
    )
    text_contex = strip_tags(html_content)

    send_mail(
        assunto,
        text_contex,
        EMAIL_HOST_USER,
        destinatario,
        html_message=html_content,
    )