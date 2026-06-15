from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from companies.models import CompanyMembership, SiteMembership

@receiver(post_delete, sender=CompanyMembership)
def eliminar_site_memberships_al_quitar_empresa(sender, instance, **kwargs):
    """
    Cuando se elimina una CompanyMembership, elimina todas las
    SiteMembership del usuario en obras de esa empresa.
    """
    SiteMembership.objects.filter(
        user=instance.user,
        site__company=instance.company,
    ).delete()