from django.db import models
from utils.utils import generate_id_random

# Create your models here.
class TypeZeladoria(models.Model):
    id_random = models.CharField(
        unique=True,
        default=generate_id_random,
        max_length=20
    )

    setor_options = [
        ('Jardinagem', 'Jardinagem'),
        ('Limpeza predial', 'Limpeza predial'),
    ]

    setor = models.CharField(
        choices=setor_options,
        null=False,
        blank=False,
        max_length=30,
        unique=True,
    )

    def __str__(self):
        return self.setor