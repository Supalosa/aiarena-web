# Generated by Django 3.2.9 on 2022-05-23 03:29

from django.db import migrations

from aiarena.core.models import Bot
from aiarena.core.models.bot_race import BotRace


def link_bot_races(apps, schema_editor):
    if Bot.objects.count() > 0:
        BotRace.create_all_races()

        for bot in Bot.objects.all():
            br = BotRace.objects.get(label=bot.plays_race)
            bot.plays_race_model_id = br.id
            bot.save()

        assert Bot.objects.filter(plays_race_model=None).count() == 0


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0047_auto_20220523_0307'),
    ]

    operations = [
        migrations.RunPython(link_bot_races),
    ]
