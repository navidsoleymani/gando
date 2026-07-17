from django.db import models

from .abstract_model_class import BaseModelClassManager, ModelClass
from .abstract_soft_delete import (
    BaseSoftDeleteManager,
    SoftDeleteBaseModelClass)


class BaseAbstractBaseModelManager(
    BaseSoftDeleteManager, BaseModelClassManager):
    def get_queryset(self) -> models.QuerySet:
        # return all objects that their is_deleted are null
        return super().get_queryset().filter(is_deleted=False, available=1)


class AbstractBaseModelManager(
    BaseAbstractBaseModelManager.from_queryset(models.QuerySet)):
    pass


class AbstractBaseModel(SoftDeleteBaseModelClass, ModelClass):
    objects = AbstractBaseModelManager()

    class Meta:
        abstract = True
