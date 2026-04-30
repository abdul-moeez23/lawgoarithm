import logging

from django.conf import settings
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from lawyers.models import LawyerProfile

logger = logging.getLogger(__name__)


def _refresh_embedding_safe(instance):
    from lawyers.training.pipeline import refresh_lawyer_embedding

    try:
        refresh_lawyer_embedding(instance)
    except Exception as exc:
        logger.warning("Lawyer embedding refresh failed for lawyer_id=%s: %s", instance.pk, exc)


@receiver(post_save, sender=LawyerProfile)
def refresh_new_lawyer_embedding(sender, instance, created, **kwargs):
    if getattr(settings, "AUTO_REFRESH_LAWYER_EMBEDDINGS", True) is False:
        return
    if instance.verification_status != "approved":
        return
    tracked_changed = getattr(instance, "_embedding_tracked_changed", False)
    needs_refresh = created or tracked_changed or not instance.embedding_vector
    if not needs_refresh:
        return
    _refresh_embedding_safe(instance)


@receiver(pre_save, sender=LawyerProfile)
def detect_embedding_affecting_changes(sender, instance, **kwargs):
    if not instance.pk:
        instance._embedding_tracked_changed = True
        return
    previous = sender.objects.filter(pk=instance.pk).only(
        "bar_enrollment",
        "city_id",
        "experience_years",
        "verification_status",
    ).first()
    if previous is None:
        instance._embedding_tracked_changed = True
        return
    instance._embedding_tracked_changed = any(
        [
            previous.bar_enrollment != instance.bar_enrollment,
            previous.city_id != instance.city_id,
            previous.experience_years != instance.experience_years,
            previous.verification_status != instance.verification_status,
        ]
    )


@receiver(m2m_changed, sender=LawyerProfile.practice_areas.through)
@receiver(m2m_changed, sender=LawyerProfile.courts.through)
def refresh_embedding_on_profile_relations(sender, instance, action, **kwargs):
    if getattr(settings, "AUTO_REFRESH_LAWYER_EMBEDDINGS", True) is False:
        return
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if instance.verification_status != "approved":
        return
    _refresh_embedding_safe(instance)
