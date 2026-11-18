from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0018_cobranza_envio_masivo"),
    ]

    operations = [
        migrations.CreateModel(
            name="IessRdepJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("anio", models.PositiveSmallIntegerField()),
                ("estado", models.CharField(choices=[("PENDIENTE", "Pendiente"), ("PROCESANDO", "Procesando"), ("COMPLETADO", "Completado"), ("ERROR", "Error")], db_index=True, default="PENDIENTE", max_length=12)),
                ("mensaje", models.CharField(blank=True, max_length=500)),
                ("archivo_relativo", models.CharField(blank=True, max_length=500)),
                ("worker_id", models.CharField(blank=True, max_length=150)),
                ("creado_en", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("iniciado_en", models.DateTimeField(blank=True, null=True)),
                ("heartbeat_en", models.DateTimeField(blank=True, null=True)),
                ("terminado_en", models.DateTimeField(blank=True, null=True)),
                ("error_detalle", models.TextField(blank=True)),
                ("cliente", models.ForeignKey(db_column="cliente_ruc", on_delete=django.db.models.deletion.PROTECT, related_name="iess_rdep_jobs", to="store.cliente", to_field="ruccedcli")),
            ],
            options={"db_table": "iess_rdep_jobs", "ordering": ["-creado_en"]},
        ),
        migrations.AddConstraint(
            model_name="iessrdepjob",
            constraint=models.UniqueConstraint(condition=models.Q(("estado__in", ["PENDIENTE", "PROCESANDO"])), fields=("cliente", "anio"), name="uq_iess_rdep_job_activo_cliente_anio"),
        ),
    ]
