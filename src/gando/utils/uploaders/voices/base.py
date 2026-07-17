import os
from uuid import uuid4
from django.utils.deconstruct import deconstructible


@deconstructible
class VoiceUploadTo(object):
    def __init__(self, sub_path='voices/'):
        self.path = sub_path

    def __call__(self, instance, filename):
        ext = filename.split('.')[-1]
        filename = '{}/{}.{}'.format(uuid4().hex, uuid4().hex, ext)
        return os.path.join(self.path, filename)
