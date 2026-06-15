from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0002_companymembership_sitemembership'),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteWeekConfig',
            fields=[
                ('id',          models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('base_monday', models.DateField(help_text='Lunes de la semana base')),
                ('base_week',   models.PositiveIntegerField(help_text='Numero de semana ISA')),
                ('prefix',      models.CharField(default='sem ', max_length=20)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('updated_at',  models.DateTimeField(auto_now=True)),
                ('site',        models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='week_config',
                    to='companies.site',
                )),
            ],
            options={
                'verbose_name': 'Configuracion de semanas ISA',
                'db_table': 'companies_site_week_config',
            },
        ),
        migrations.CreateModel(
            name='SiteCargoValor',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('cargo',      models.CharField(max_length=120)),
                ('valor_hh',   models.DecimalField(max_digits=10, decimal_places=2)),
                ('is_active',  models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('site',       models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cargo_valores',
                    to='companies.site',
                )),
            ],
            options={
                'verbose_name': 'Valor HH por cargo',
                'db_table': 'companies_site_cargo_valor',
                'ordering': ['site', 'cargo'],
            },
        ),
        migrations.AddConstraint(
            model_name='sitecargovalor',
            constraint=models.UniqueConstraint(
                fields=['site', 'cargo'],
                name='unique_cargo_valor_per_site'
            ),
        ),
    ]
