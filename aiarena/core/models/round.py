import logging

from constance import config
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from aiarena.api.arenaclient.exceptions import NoMaps, NotEnoughActiveBots, CurrentSeasonPaused, CurrentSeasonClosing
from .map import Map
from .mixins import LockableModelMixin
from .season import Season

logger = logging.getLogger(__name__)


class Round(models.Model, LockableModelMixin):
    """ Represents a round of play within a season """
    number = models.IntegerField(blank=True, editable=False)
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    started = models.DateTimeField(auto_now_add=True)
    finished = models.DateTimeField(blank=True, null=True)
    complete = models.BooleanField(default=False)

    @property
    def name(self):
        return 'Round ' + str(self.number)

    def __str__(self):
        return self.name

    # if all the matches have been run, mark this as complete
    def update_if_completed(self):
        from .match import Match
        self.lock_me()

        # if there are no matches without results, this round is complete
        if Match.objects.filter(round=self, result__isnull=True).count() == 0:
            self.complete = True
            self.finished = timezone.now()
            self.save()
            Season.get_current_season().try_to_close()

    @staticmethod
    def max_active_rounds_reached():
        return Round.objects.filter(complete=False).count() >= config.MAX_ACTIVE_ROUNDS

    @staticmethod
    def generate_new():
        from . import Bot, Match
        if Map.objects.filter(active=True).count() == 0:
            raise NoMaps()  # todo: separate between core and API exceptions
        if Bot.objects.filter(active=True).count() <= 1:  # need at least 2 active bots for a match
            raise NotEnoughActiveBots()  # todo: separate between core and API exceptions

        current_season = Season.get_current_season()
        if current_season.is_paused:
            raise CurrentSeasonPaused()
        if current_season.is_closing:  # we should technically never hit this
            raise CurrentSeasonClosing()

        new_round = Round.objects.create(season=Season.get_current_season())

        active_bots = Bot.objects.filter(active=True)
        already_processed_bots = []

        # loop through and generate matches for all active bots
        for bot1 in active_bots:
            already_processed_bots.append(bot1.id)
            for bot2 in Bot.objects.filter(active=True).exclude(id__in=already_processed_bots):
                Match.create(new_round, Map.random_active(), bot1, bot2)

    def get_absolute_url(self):
        return reverse('round', kwargs={'pk': self.pk})

    def as_html_link(self):
        return '<a href="{0}">{1}</a>'.format(self.get_absolute_url(), escape(self.__str__()))


@receiver(pre_save, sender=Round)
def pre_save_round(sender, instance, **kwargs):
    if instance.number is None:
        instance.number = Round.objects.filter(season=instance.season).count() + 1