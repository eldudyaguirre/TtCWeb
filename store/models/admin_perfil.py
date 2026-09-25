from django.db import models


class AdminPerfil(models.Model):
    usuario = models.CharField(max_length=150, unique=True)
    nombres = models.CharField(max_length=200, blank=True)
    direccion = models.CharField(max_length=300, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    foto = models.ImageField(
        upload_to='admin/perfiles/',
        blank=True,
        null=True,
    )

    class Meta:
        db_table = 'admin_perfil'
        verbose_name = 'Perfil administrativo'
        verbose_name_plural = 'Perfiles administrativos'

    def __str__(self):
        return self.usuario
