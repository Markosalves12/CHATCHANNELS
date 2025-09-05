from django.db import models
from empresaprimaria.models import EmpresaPrimaria
from utils.utils import resize_image
from utils.utils import generate_id_random
from zeladorx.models import TypeZeladoria

# Create your models here.
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

    # razao_social = models.CharField(
    #     blank=False,
    #     null=False,
    #     max_length=120,
    # )
    #
    # CNPJ = models.CharField(
    #     blank=False,
    #     null=False,
    #     max_length=40,
    # )
    #
    # logo = models.ImageField(
    #     upload_to="media/%Y/%m/%d/",
    #     blank=True,
    #     max_length=1000
    # )

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
        null=False,
        to=TypeZeladoria,
        max_length=40
    )

    empresaprimaria = models.ForeignKey(
        to=EmpresaPrimaria,
        blank=False,
        null=False,
        on_delete=models.CASCADE,
        related_name='REmpresaPrimaria'
    )

    # def save(self, *args, **kwargs):
    #     if self.logo:
    #         self.logo = resize_image(self.logo, max_width=40)
    #
    #     super(EmpresaSecundaria, self).save(*args, **kwargs)

    def __str__(self):
        setores = ", ".join(setor.setor for setor in self.setor.all())
        return f'{self.nome} | {setores}'
