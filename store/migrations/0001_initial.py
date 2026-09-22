import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UsuarioCliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rol', models.CharField(
                    choices=[
                        ('ADMIN', 'Administrador'),
                        ('OPERADOR', 'Operador'),
                        ('CONSULTA', 'Consulta'),
                    ],
                    default='OPERADOR',
                    max_length=10,
                )),
                ('activo', models.BooleanField(default=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('cliente', models.ForeignKey(
                    db_column='ruccedcli',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='usuarios_asignados',
                    to='store.cliente',
                )),
                ('usuario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='clientes_asignados',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'usuarios_clientes',
                'ordering': ['cliente__nomclient', 'usuario__username'],
                'verbose_name': 'Usuario por cliente',
                'verbose_name_plural': 'Usuarios por cliente',
            },
        ),
        migrations.AddConstraint(
            model_name='usuariocliente',
            constraint=models.UniqueConstraint(
                fields=('usuario', 'cliente'),
                name='uq_usuario_cliente',
            ),
        ),
    ]
