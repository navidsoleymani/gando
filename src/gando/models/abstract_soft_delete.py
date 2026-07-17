from django.db import models
from django.utils.translation import gettext_lazy as _

from .base import current_user_id, current_user_agent_info


class BaseSoftDeleteManager(models.Manager):
    def get_queryset(self) -> models.QuerySet:
        # return all objects that their is_deleted are null
        return super().get_queryset().filter(is_deleted=False)

    def delete(self):
        from django.utils.timezone import now as dj_now

        return self.update(
            is_deleted=True,
            deleted_dt=dj_now(),
            deleted_by=current_user_id(),
            deleted_by_user_agent_info=current_user_agent_info(),
        )


class SoftDeleteManager(
    BaseSoftDeleteManager.from_queryset(models.QuerySet)):
    pass


class SoftDeleteBaseModelClass(models.Model):
    is_deleted = models.BooleanField(
        verbose_name=_('Deleted'),
        blank=False,
        null=False,
        default=False,
        db_index=True,
        help_text=_(
            'This field indicates whether '
            'this record has been deleted(soft delete) or not.'),
    )
    deleted_dt = models.DateTimeField(
        verbose_name=_('Deleted Datetime'),
        blank=True,
        null=True,
        help_text=_(
            'This field displays the date and '
            'time when this record was deleted(soft delete).'),
    )
    deleted_by = models.UUIDField(
        verbose_name=_('Deleted By...(ID)'),
        blank=True,
        null=True,
        help_text=_(
            'This field displays who deleted(soft delete) the record.'),
    )
    deleted_by_user_agent_info = models.JSONField(
        verbose_name=_('Deleted By...(User Agent Info)'),
        blank=True,
        null=True,
        help_text=_(
            'This field displays information about the user(user agent) '
            'who deleted(soft delete) this record.')
    )

    # enforce manager
    objects = SoftDeleteManager()

    def delete(self, **kwargs):
        from django.utils.timezone import now as dj_now

        self.is_deleted = True
        self.deleted_dt = dj_now()
        self.deleted_by = current_user_id()
        self.deleted_by_user_agent_info = current_user_agent_info()
        self.save()

    def force_delete(self):
        super().delete()

    class Meta:
        abstract = True
