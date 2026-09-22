from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0004_aceptacionlegal_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='aceptacionlegal',
            name='ip_address',
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='aceptacionlegal',
            name='user_agent',
            field=models.TextField(blank=True),
        ),
    ]
