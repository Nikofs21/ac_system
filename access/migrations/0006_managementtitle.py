# -*- coding: utf-8 -*-
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0005_siteworkdayconfig_autoclose_and_vigencia'),
        ('access', '0005_role_is_protected_user_is_novus_super'),
    ]

    operations = [
        migrations.CreateModel(
            name='ManagementTitle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='management_titles', to='companies.company')),
            ],
            options={
                'verbose_name': 'Cargo de gerencia',
                'verbose_name_plural': 'Cargos de gerencia',
                'db_table': 'access_management_title',
                'ordering': ['name'],
            },
        ),
        migrations.AddConstraint(
            model_name='managementtitle',
            constraint=models.UniqueConstraint(fields=('company', 'name'), name='unique_management_title_per_company'),
        ),
    ]
