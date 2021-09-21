from django.db import models
from utils.constants import StateType
import uuid


def generate_id():
    return uuid.uuid4().hex


class BaseAbstractModel(models.Model):
    """ Base Abstract Model """

    id = models.CharField(
        max_length=60, primary_key=True, default=generate_id, editable=False
    )
    state = models.CharField(
        max_length=50,
        choices=[(state.name, state.value) for state in StateType],
        default="active",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def update(self, **kwargs):
        if self._state.adding:
            raise self.DoesNotExist
        for field, value in kwargs.items():
            setattr(self, field, value)
        self.save(update_fields=kwargs.keys())
        return self
