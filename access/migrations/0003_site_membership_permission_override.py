from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('access', '0002_permission_role_userpreference_rolepermission'),
        ('companies', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteMembershipPermissionOverride',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('granted',    models.BooleanField(help_text='True = agregar permiso, False = quitar permiso')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('site_membership', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='permission_overrides',
                    to='companies.sitemembership',
                )),
                ('permission', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='membership_overrides',
                    to='access.permission',
                )),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='permission_overrides_created',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Override de permiso por membresia',
                'verbose_name_plural': 'Overrides de permiso por membresia',
                'db_table': 'access_membership_permission_override',
            },
        ),
        migrations.AddConstraint(
            model_name='sitemembershippermissionoverride',
            constraint=models.UniqueConstraint(
                fields=['site_membership', 'permission'],
                name='unique_override_per_membership_permission'
            ),
        ),
    ]
