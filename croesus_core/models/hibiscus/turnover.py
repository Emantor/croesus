from django.db.models import (
    BooleanField,
    FloatField,
    Case,
    When,
    Max,
    Min,
    Sum,
    F,
)

from django.apps import apps
from django.db import models

from ...utils.serializers import PrettyYamlSerializer
from ...utils.buffers import write_title
from ...utils.time import MONTH_NAMES

__all__ = [
    'HibiscusTurnover',
]


class HibiscusTurnoverQuerySet(models.QuerySet):
    def match_ibans(self):
        for turnover in self.iterator():
            turnover.match_iban()

    def dump(self, buffer, bookings=False):
        dates = self.aggregate(Max('date'), Min('date'))
        year_min = dates['date__min'].year
        year_max = dates['date__max'].year
        first_year_month_min = dates['date__min'].month
        last_year_month_max = dates['date__max'].month

        for index, year in enumerate(range(year_min, year_max + 1)):
            month_min = 1
            month_max = 12

            if year == year_min:
                month_min = first_year_month_min

            if year == year_max:
                month_max = last_year_month_max

            for month in range(month_min, month_max + 1):
                write_title(buffer, '{} {}'.format(year,
                                                   MONTH_NAMES[month - 1]))

                sub_qs = self.filter(date__year=year, date__month=month)

                for turnover in sub_qs:
                    turnover.dump(buffer)

                    buffer.write('\n')


class HibiscusTurnoverManager(models.Manager):
    def get_queryset(self):
        return HibiscusTurnoverQuerySet(
            self.model,
            using=self._db,
        ).annotate(
            bookings_amount=Sum('bookings__amount'),
        ).annotate(
            underbooked=Case(
                When(bookings_amount__isnull=True, then=True),
                When(bookings_amount__lt=F('amount'), then=True),
                output_field=BooleanField(),
                default=False,
            ),
            booked=Case(
                When(bookings_amount__gte=F('amount'), then=True),
                output_field=BooleanField(),
                default=False,
            ),
            overbooked=Case(
                When(bookings_amount__gt=F('amount'), then=True),
                output_field=BooleanField(),
                default=False,
            ),
            bookable=Case(
                When(bookings_amount__isnull=False,
                     then=F('amount') - F('bookings_amount')),
                output_field=FloatField(),
                default=F('amount'),
            ),
        )


class HibiscusTurnover(models.Model):
    objects = HibiscusTurnoverManager()

    account_id = models.IntegerField(verbose_name='Account Id')
    turnover_id = models.IntegerField(verbose_name='Turnover Id')
    type = models.TextField(blank=True, null=True, verbose_name='Type')
    balance = models.FloatField(blank=True, null=True, verbose_name='Balance')
    amount = models.FloatField(blank=True, null=True, verbose_name='Amount')
    date = models.DateField(blank=True, null=True, verbose_name='Date')

    name = models.CharField(max_length=100, blank=True, null=True,
                            verbose_name='Name')
    customer_ref = models.TextField(blank=True, null=True,
                                    verbose_name='Customer Ref')
    iban = models.CharField(max_length=30, blank=True, null=True,
                            verbose_name='IBAN')
    bic = models.CharField(max_length=11, blank=True, null=True,
                           verbose_name='BIC')
    purpose = models.TextField(blank=True, null=True, verbose_name='Purpose')
    comment = models.TextField(blank=True, null=True, verbose_name='Comment')

    commercial_transaction_code = models.PositiveIntegerField(
        blank=True, null=True, verbose_name='Commercial Transaction Code')
    primanota = models.PositiveIntegerField(blank=True, null=True,
                                            verbose_name='Primanota')
    value_date = models.DateField(blank=True, null=True)

    person = models.ForeignKey('croesus_core.Person', blank=True, null=True,
                               verbose_name='Person')

    def book(self, account, amount):
        Booking = apps.get_model('croesus_core', 'Booking')

        return Booking.objects.create(
            turnover=self,
            account=account,
            amount=amount,
        )

    def match_iban(self):
        PersonAccount = apps.get_model('croesus_core', 'PersonAccount')

        if not self.iban:
            return

        pa = PersonAccount.objects.filter(iban=self.iban)

        if pa.count() == 1:
            self.person = pa[0].person
            self.save()

    def dump(self, buffer, bookings=False):
        serializer = PrettyYamlSerializer()

        serializer.serialize([self], stream=buffer)

    def __str__(self):
        return '<HibiscusTurnover:{}, {}, {}, {}>'.format(
                self.pk,
                self.person,
                self.date,
                self.amount
        )

    class Meta:
        app_label = 'croesus_core'
        unique_together = ('account_id', 'turnover_id', )
        ordering = ['account_id', 'turnover_id']
