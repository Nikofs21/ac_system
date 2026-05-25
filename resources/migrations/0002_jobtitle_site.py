# resources/migrations/0002_jobtitle_site.py
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0001_initial'),
        ('companies', '0002_companymembership_sitemembership'),
    ]

    operations = [
        migrations.AddField(
            model_name='jobtitle',
            name='site',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='job_titles',
                to='companies.site',
            ),
        ),
        # Actualizar el unique constraint: ahora es (company, site, name)
        # donde site puede ser null (cargo de empresa) o un id (cargo de obra)
        migrations.AlterUniqueTogether(
            name='jobtitle',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='jobtitle',
            constraint=models.UniqueConstraint(
                fields=['company', 'site', 'name'],
                name='unique_job_title_per_company_site',
            ),
        ),
    ]
