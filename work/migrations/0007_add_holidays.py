from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0006_alter_worksessionchangelog_change_type_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        migrations.CreateModel(
            name='ChilePublicHoliday',
            fields=[
                ('id',           models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('date',         models.DateField(unique=True)),
                ('name',         models.CharField(max_length=120)),
                ('year',         models.SmallIntegerField()),
                ('is_recurring', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Feriado nacional Chile',
                'verbose_name_plural': 'Feriados nacionales Chile',
                'db_table': 'work_chile_public_holiday',
                'ordering': ['date'],
            },
        ),

        migrations.CreateModel(
            name='SiteHoliday',
            fields=[
                ('id',          models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('date',        models.DateField()),
                ('description', models.CharField(max_length=180)),
                ('is_active',   models.BooleanField(default=True)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('site',        models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='holidays',
                    to='companies.site',
                )),
                ('created_by',  models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='site_holidays_created',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Dia no laborable por obra',
                'verbose_name_plural': 'Dias no laborables por obra',
                'db_table': 'work_site_holiday',
                'ordering': ['site', 'date'],
            },
        ),
        migrations.AddConstraint(
            model_name='siteholiday',
            constraint=models.UniqueConstraint(
                fields=['site', 'date'],
                name='unique_site_holiday_per_date'
            ),
        ),
    ]
