"""A tiny Django app used only to exercise gando's abstract base models.

It exists purely for the test suite: :mod:`gando` ships only *abstract*
models (``AbstractBaseModel`` and friends), so a concrete model in a real
installed app is required to test the manager/soft-delete/audit behavior
against an actual database table.
"""
