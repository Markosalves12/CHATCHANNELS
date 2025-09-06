from django.db import models
from empresaprimaria.models import EmpresaPrimaria
from utils.utils import generate_id_random
from zeladorx.models import TypeZeladoria

class EmpresaSecundaria(models.Model):
    id_random = models.CharField(
        unique=True,
        default=generate_id_random,
        max_length=20
    )

    nome = models.CharField(
        blank=False,
        null=False,
        max_length=40
    )

    status_options = [
        ('Mobilizado', 'Mobilizado'),
        ('Desmobilizado', 'Desmobilizado'),
    ]

    status = models.CharField(
        max_length=60,
        blank=False,
        null=False,
        choices=status_options,
        default='Mobilizado'
    )

    setor = models.ManyToManyField(
        blank=False,
        to=TypeZeladoria
    )

    empresaprimaria = models.ForeignKey(
        to=EmpresaPrimaria,
        blank=False,
        null=False,
        on_delete=models.CASCADE,
        related_name='REmpresaPrimaria'
    )

    def __str__(self):
        setores = ", ".join(setor.setor for setor in self.setor.all())
        return f'{self.nome} | {setores}'
