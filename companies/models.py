# -*- coding: utf-8 -*-
from django.db import models
from django.conf import settings


class Company(models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activa'
        INACTIVE = 'INACTIVE', 'Inactiva'
        ARCHIVED = 'ARCHIVED', 'Archivada'

    name = models.CharField(max_length=180)
    code = models.CharField(max_length=30, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    tax_id = models.CharField(max_length=30, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=30, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='companies_created'
    )

    class Meta:
        db_table = 'companies_company'
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'


class Site(models.Model):

    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planificada'
        ACTIVE = 'ACTIVE', 'Activa'
        PAUSED = 'PAUSED', 'Pausada'
        CLOSED = 'CLOSED', 'Cerrada'
        ARCHIVED = 'ARCHIVED', 'Archivada'

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name='sites'
    )
    name = models.CharField(max_length=180)
    code = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    timezone = models.CharField(max_length=64, default='America/Santiago')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'companies_site'
        verbose_name = 'Obra'
        verbose_name_plural = 'Obras'
        ordering = ['company', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'code'],
                name='unique_site_code_per_company'
            )
        ]

    def __str__(self):
        return f'{self.name} ({self.code}) - {self.company.name}'


class CompanyConfig(models.Model):

    class ControlMode(models.TextChoices):
        PERSONAS = 'PERSONAS', 'Solo personas'
        MAQUINARIAS = 'MAQUINARIAS', 'Solo maquinarias'
        MIXTA = 'MIXTA', 'Mixta'

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name='config'
    )
    control_mode = models.CharField(
        max_length=20,
        choices=ControlMode.choices,
        default=ControlMode.PERSONAS
    )
    allow_people = models.BooleanField(default=True)
    allow_machinery = models.BooleanField(default=False)
    allow_subcontracts = models.BooleanField(default=True)
    allow_orgchart = models.BooleanField(default=False)
    allow_planning = models.BooleanField(default=False)
    allow_assistance = models.BooleanField(default=False)
    allow_payroll = models.BooleanField(default=False)
    allow_google_sheet_export = models.BooleanField(default=False)
    allow_internal_dashboard = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'companies_company_config'
        verbose_name = 'Configuracion de empresa'
        verbose_name_plural = 'Configuraciones de empresa'

    def __str__(self):
        return f'Config - {self.company.name}'


class SiteConfig(models.Model):

    site = models.OneToOneField(
        Site,
        on_delete=models.CASCADE,
        related_name='config'
    )
    use_people = models.BooleanField(default=True)
    use_machinery = models.BooleanField(default=False)
    use_subcontracts = models.BooleanField(default=True)
    use_orgchart = models.BooleanField(default=False)
    use_planning = models.BooleanField(default=False)
    use_assistance = models.BooleanField(default=False)
    use_internal_dashboard = models.BooleanField(default=False)
    show_supervisor_dashboard = models.BooleanField(default=False)
    show_admin_dashboard = models.BooleanField(default=False)
    show_aac_dashboard = models.BooleanField(default=False)
    enable_no_on_site_tracking = models.BooleanField(default=True)
    enable_no_on_site_alert_only = models.BooleanField(default=True)
    high_risk_email_batch_minutes = models.IntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'companies_site_config'
        verbose_name = 'Configuracion de obra'
        verbose_name_plural = 'Configuraciones de obra'

    def __str__(self):
        return f'Config - {self.site.name}'


class SiteWorkdayConfig(models.Model):

    class Weekday(models.IntegerChoices):
        MONDAY = 0, 'Lunes'
        TUESDAY = 1, 'Martes'
        WEDNESDAY = 2, 'Miercoles'
        THURSDAY = 3, 'Jueves'
        FRIDAY = 4, 'Viernes'
        SATURDAY = 5, 'Sabado'
        SUNDAY = 6, 'Domingo'

    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name='workday_configs'
    )
    weekday = models.IntegerField(choices=Weekday.choices)
    work_start_time = models.TimeField()
    work_end_time = models.TimeField()
    lunch_start_time = models.TimeField(null=True, blank=True)
    lunch_end_time = models.TimeField(null=True, blank=True)
    deduct_lunch_from_icc = models.BooleanField(default=True)
    all_day_overtime = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'companies_site_workday_config'
        verbose_name = 'Configuracion de jornada'
        verbose_name_plural = 'Configuraciones de jornada'
        constraints = [
            models.UniqueConstraint(
                fields=['site', 'weekday'],
                name='unique_workday_per_site'
            )
        ]

    def __str__(self):
        return f'{self.site.name} - {self.get_weekday_display()}'

class CompanyMembership(models.Model):

    class MembershipType(models.TextChoices):
        PROVIDER = 'PROVIDER', 'Prestador'
        CLIENT_COMPANY = 'CLIENT_COMPANY', 'Cliente empresa'
        CLIENT_SITE = 'CLIENT_SITE', 'Cliente obra'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_memberships'
    )
    company = models.ForeignKey(
        'Company',
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    membership_type = models.CharField(
        max_length=20,
        choices=MembershipType.choices
    )
    is_active = models.BooleanField(default=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='memberships_granted'
    )
    started_at = models.DateField(null=True, blank=True)
    ended_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'companies_company_membership'
        verbose_name = 'Membresia de empresa'
        verbose_name_plural = 'Membresias de empresa'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'company'],
                name='unique_user_company_membership'
            )
        ]

    def __str__(self):
        return f'{self.user.get_full_name()} - {self.company.name} ({self.membership_type})'


class SiteMembership(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='site_memberships'
    )
    site = models.ForeignKey(
        'Site',
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    role = models.ForeignKey(
        'access.Role',
        on_delete=models.PROTECT,
        related_name='site_memberships'
    )
    is_active = models.BooleanField(default=True)
    can_operate = models.BooleanField(default=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='site_memberships_granted'
    )
    started_at = models.DateField(null=True, blank=True)
    ended_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'companies_site_membership'
        verbose_name = 'Membresia de obra'
        verbose_name_plural = 'Membresias de obra'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'site'],
                name='unique_user_site_membership'
            )
        ]

    def __str__(self):
        return f'{self.user.get_full_name()} - {self.site.name} ({self.role.name})'

class SiteWeekConfig(models.Model):
    """
    Configuracion de semanas ISA por obra.
    Define desde cuando empieza a contar el sistema y que numero de semana corresponde.
    Ejemplo: lunes 04-05-2026 = semana 20.
    A partir de ahi el sistema calcula automaticamente la semana de cada sesion.
    """
    site        = models.OneToOneField(
        Site,
        on_delete=models.CASCADE,
        related_name='week_config'
    )
    base_monday = models.DateField(
        help_text='Lunes de la semana base. Ej: 04-05-2026'
    )
    base_week   = models.PositiveIntegerField(
        help_text='Numero de semana ISA que corresponde a ese lunes. Ej: 20'
    )
    prefix      = models.CharField(
        max_length=20,
        default='sem ',
        help_text='Prefijo para el nombre de semana. Default: "sem "'
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = 'companies_site_week_config'
        verbose_name = 'Configuracion de semanas ISA'
        verbose_name_plural = 'Configuraciones de semanas ISA'

    def get_week_for_date(self, date):
        """Retorna el numero de semana ISA para una fecha dada."""
        from datetime import timedelta
        # Obtener lunes de la semana de la fecha
        days_since_monday = date.weekday()
        week_monday = date - timedelta(days=days_since_monday)
        # Calcular diferencia en semanas respecto al lunes base
        diff_days  = (week_monday - self.base_monday).days
        diff_weeks = diff_days // 7
        return self.base_week + diff_weeks

    def get_week_label_for_date(self, date):
        """Retorna el label de semana para una fecha. Ej: 'sem 23'"""
        return f'{self.prefix}{self.get_week_for_date(date)}'

    def __str__(self):
        return f'{self.site.name} — base: {self.base_monday} = {self.prefix}{self.base_week}'


class SiteCargoValor(models.Model):
    """
    Valor de HH por cargo en una obra especifica.
    Se usa para calcular costo HH en el Excel de exportacion RRA.
    Varia por obra y puede actualizarse cuando llega el Libro de Remuneraciones.
    """
    site       = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name='cargo_valores'
    )
    cargo      = models.CharField(
        max_length=120,
        help_text='Nombre del cargo exactamente como aparece en las sesiones'
    )
    valor_hh   = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text='Valor en pesos por hora hombre'
    )
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table     = 'companies_site_cargo_valor'
        verbose_name = 'Valor HH por cargo'
        verbose_name_plural = 'Valores HH por cargo'
        ordering     = ['site', 'cargo']
        constraints  = [
            models.UniqueConstraint(
                fields=['site', 'cargo'],
                name='unique_cargo_valor_per_site'
            )
        ]

    def __str__(self):
        return f'{self.site.name} — {self.cargo}: ${self.valor_hh}/HH'