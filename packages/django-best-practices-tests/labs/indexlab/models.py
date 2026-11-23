"""Models whose indexes and constraints the index- rules inspect with EXPLAIN and catalog queries."""

from django.conf import settings
from django.db import models


class Account(models.Model):
    name = models.CharField(max_length=50)


class Ticket(models.Model):
    # Not indexed on its own: the leading column of the unique constraint covers it.
    account = models.ForeignKey(Account, on_delete=models.PROTECT, db_index=False)
    number = models.IntegerField()
    # Indexed in Meta, only where it is set.
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, db_index=False
    )
    opened_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['account', 'number'], name='ticket_account_number_uk'),
        ]
        indexes = [
            models.Index(
                fields=['assignee'],
                name='ticket_assignee_part_ix',
                condition=models.Q(assignee__isnull=False),
            ),
        ]


class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_index=False)
    team = models.CharField(max_length=30)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'team'],
                condition=models.Q(active=True),
                name='membership_one_active_per_team_uk',
            ),
        ]


class Voucher(models.Model):
    code = models.CharField(max_length=20, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['code'], name='voucher_code_uk', nulls_distinct=False),
        ]
