# -*- coding: utf-8 -*-
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0005_siteworkdayconfig_autoclose_and_vigencia'),
        ('access', '0006_managementtitle'),
    ]

    operations = [
        migrations.AddField(
            model_name='companymembership',
            name='management_title',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='company_memberships',
                to='access.managementtitle',
                help_text='Sub-cargo de gerencia (solo aplica si el usuario tiene rol gerencia en alguna obra de esta empresa).',
            ),
        ),
    ]
