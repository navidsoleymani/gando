import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from gando.models.fields import (
    UUIDContinuousCommunicationField,
    JSONContinuousCommunicationField,
)
from .base import current_user_id, current_user_agent_info


class BaseModelClassManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(available=1)
        return queryset


class ModelClassManager(
    BaseModelClassManager.from_queryset(models.QuerySet)):
    pass


class ModelClass(models.Model):
    id = models.UUIDField(
        verbose_name=_('ID'),
        primary_key=True,
        default=uuid.uuid7,
        blank=False,
        null=False,
        unique=True,
        editable=False,
        db_index=True,
    )
    created_dt = models.DateTimeField(
        verbose_name=_('Created Datetime'),
        auto_now_add=True,
        db_index=True,
        help_text=_(
            'This field indicates when and '
            'on what date this record was created.')
    )
    created_by = UUIDContinuousCommunicationField(
        verbose_name=_('Created By...(ID)'),
        blank=True,
        null=True,
        auto_now_add=True,
        ito=current_user_id,
        help_text=_('This field indicates who created this record.'),
    )
    created_by_user_agent_info = JSONContinuousCommunicationField(
        verbose_name=_('Created By...(User Agent Info)'),
        blank=True,
        null=True,
        auto_now_add=True,
        ito=current_user_agent_info,
        help_text=_(
            'This field stores information about the user(user agent) '
            'who created this field.'),
    )

    updated_dt = models.DateTimeField(
        verbose_name=_('Last Updated Datetime'),
        auto_now=True,
        db_index=True,
        help_text=_(
            'This field displays the time and date '
            'this record was last updated.'),
    )
    last_updated_by = UUIDContinuousCommunicationField(
        verbose_name=_('Last Updated By...(ID)'),
        blank=True,
        null=True,
        auto_now=True,
        ito=current_user_id,
        help_text=_('This field displays who last updated this record.'),
    )
    last_updated_by_user_agent_info = JSONContinuousCommunicationField(
        verbose_name=_('Last Updated By...(User Agent Info)'),
        blank=True,
        null=True,
        auto_now=True,
        ito=current_user_agent_info,
        help_text=_(
            'This field displays the information of the user(user agent) '
            'who last updated this record.')
    )

    server_side_settings = models.JSONField(
        verbose_name=_('Server-Side Settings'),
        blank=True,
        null=True,
        help_text=_(
            'If you need to have specific settings for each record in '
            'this table on the server side, '
            'you can save these settings in this section.'),
    )
    client_side_settings = models.JSONField(
        verbose_name=_('Client-Side Settings'),
        blank=True,
        null=True,
        help_text=_(
            'If you need to have specific settings for each record in '
            'this table on the client side, '
            'you can save these settings in this section.'),
    )
    available = models.IntegerField(
        verbose_name=_('Available'),
        default=1,
        choices=(
            (0, 'No'),
            (1, 'Yes'),
        ),
        db_index=True,
    )
    # enforce manager
    objects = ModelClassManager()

    class Meta:
        abstract = True

    history = HistoricalRecords(inherit=True)

    def __str__(self):
        return str(self.id)
