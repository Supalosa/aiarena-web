import io

from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from django.db import connection
from django.db.models import Max, Min
from pytz import utc

from aiarena.core.models import MatchParticipation, CompetitionParticipation, Bot
from aiarena.core.models.competition_bot_matchup_stats import CompetitionBotMatchupStats
from aiarena.core.models.competition_bot_map_stats import CompetitionBotMapStats
from aiarena.core.models.competition import Competition

class StatsGenerator:

    @staticmethod
    def update_stats(sp: CompetitionParticipation):
        sp.match_count = MatchParticipation.objects.filter(bot=sp.bot,
                                                           match__result__isnull=False,
                                                           match__round__competition=sp.competition) \
            .exclude(match__result__type__in=['MatchCancelled', 'InitializationError', 'Error']) \
            .count()
        if sp.match_count != 0:
            sp.win_count = MatchParticipation.objects.filter(bot=sp.bot, result='win',
                                                             match__round__competition=sp.competition
                                                             ).count()
            sp.win_perc = sp.win_count / sp.match_count * 100
            sp.loss_count = MatchParticipation.objects.filter(bot=sp.bot, result='loss',
                                                              match__round__competition=sp.competition
                                                              ).count()
            sp.loss_perc = sp.loss_count / sp.match_count * 100
            sp.tie_count = MatchParticipation.objects.filter(bot=sp.bot, result='tie',
                                                             match__round__competition=sp.competition
                                                             ).count()
            sp.tie_perc = sp.tie_count / sp.match_count * 100
            sp.crash_count = MatchParticipation.objects.filter(bot=sp.bot, result='loss', result_cause__in=['crash',
                                                                                                            'timeout',
                                                                                                            'initialization_failure'],
                                                               match__round__competition=sp.competition
                                                               ).count()
            sp.crash_perc = sp.crash_count / sp.match_count * 100

            sp.highest_elo = MatchParticipation.objects.filter(bot=sp.bot,
                                                               match__result__isnull=False,
                                                               match__round__competition=sp.competition) \
                .aggregate(Max('resultant_elo'))['resultant_elo__max']

            graph1, graph2 = StatsGenerator._generate_elo_graph(sp.bot.id, sp.competition_id)
            if graph1 is not None:
                sp.elo_graph.save('elo.png', graph1)

            if graph2 is not None:
                sp.elo_graph_update_plot.save('elo_update_plot.png', graph2)
        else:
            sp.win_count = 0
            sp.loss_count = 0
            sp.tie_count = 0
            sp.crash_count = 0
        sp.save()

        StatsGenerator._update_matchup_stats(sp)
        StatsGenerator._update_map_stats(sp)

    @staticmethod
    def _update_matchup_stats(sp: CompetitionParticipation):
        for competition_participation in CompetitionParticipation.objects.filter(competition=sp.competition).exclude(
                bot=sp.bot):
            with connection.cursor() as cursor:
                matchup_stats = CompetitionBotMatchupStats.objects.select_for_update() \
                    .get_or_create(bot=sp, opponent=competition_participation)[0]

                matchup_stats.match_count = StatsGenerator._calculate_matchup_count(cursor, competition_participation,
                                                                                    sp)

                if matchup_stats.match_count != 0:
                    matchup_stats.win_count = StatsGenerator._calculate_matchup_win_count(cursor, competition_participation, sp)
                    matchup_stats.win_perc = matchup_stats.win_count / matchup_stats.match_count * 100

                    matchup_stats.loss_count = StatsGenerator._calculate_matchup_loss_count(cursor, competition_participation,
                                                                                    sp)
                    matchup_stats.loss_perc = matchup_stats.loss_count / matchup_stats.match_count * 100

                    matchup_stats.tie_count = StatsGenerator._calculate_matchup_tie_count(cursor, competition_participation, sp)
                    matchup_stats.tie_perc = matchup_stats.tie_count / matchup_stats.match_count * 100

                    matchup_stats.crash_count = StatsGenerator._calculate_matchup_crash_count(cursor, competition_participation,
                                                                                      sp)
                    matchup_stats.crash_perc = matchup_stats.crash_count / matchup_stats.match_count * 100
                else:
                    matchup_stats.win_count = 0
                    matchup_stats.loss_count = 0
                    matchup_stats.tie_count = 0
                    matchup_stats.crash_count = 0

                matchup_stats.save()

    @staticmethod
    def _update_map_stats(sp: CompetitionParticipation):
        competition = Competition.objects.get(id=sp.competition.id)
        for map in competition.maps.all():
            with connection.cursor() as cursor:
                map_stats = CompetitionBotMapStats.objects.select_for_update() \
                    .get_or_create(bot=sp, map=map)[0]

                map_stats.match_count = StatsGenerator._calculate_map_count(cursor, map, sp)

                if map_stats.match_count != 0:
                    map_stats.win_count = StatsGenerator._calculate_map_win_count(cursor, map, sp)
                    map_stats.win_perc = map_stats.win_count / map_stats.match_count * 100

                    map_stats.loss_count = StatsGenerator._calculate_map_loss_count(cursor, map, sp)
                    map_stats.loss_perc = map_stats.loss_count / map_stats.match_count * 100

                    map_stats.tie_count = StatsGenerator._calculate_map_tie_count(cursor, map, sp)
                    map_stats.tie_perc = map_stats.tie_count / map_stats.match_count * 100

                    map_stats.crash_count = StatsGenerator._calculate_map_crash_count(cursor, map, sp)
                    map_stats.crash_perc = map_stats.crash_count / map_stats.match_count * 100
                else:
                    map_stats.win_count = 0
                    map_stats.loss_count = 0
                    map_stats.tie_count = 0
                    map_stats.crash_count = 0

                map_stats.save()

    @staticmethod
    def _run_single_column_query(cursor, query, params):
        cursor.execute(query, params)
        row = cursor.fetchone()
        return row[0]

    @staticmethod
    def _calculate_matchup_data(cursor, competition_participation, sp, query):
        return StatsGenerator._run_single_column_query(cursor, """
                    select count(cm.id) as count
                    from core_match cm
                    inner join core_matchparticipation bot_p on cm.id = bot_p.match_id
                    inner join core_matchparticipation opponent_p on cm.id = opponent_p.match_id
                    inner join core_round cr on cm.round_id = cr.id
                    inner join core_competition cs on cr.competition_id = cs.id
                    where cs.id = %s -- make sure it's part of the current competition
                    and bot_p.bot_id = %s
                    and opponent_p.bot_id = %s
                    and """ + query, 
                    [sp.competition_id, sp.bot_id, competition_participation.bot_id])

    @staticmethod
    def _calculate_matchup_count(cursor, competition_participation, sp):
        return StatsGenerator._calculate_matchup_data(cursor, competition_participation, sp,
                    "bot_p.result is not null and bot_p.result != 'none'")

    @staticmethod
    def _calculate_matchup_win_count(cursor, competition_participation, sp):
        return StatsGenerator._calculate_matchup_data(cursor, competition_participation, sp,
                    "bot_p.result = 'win'")

    @staticmethod
    def _calculate_matchup_loss_count(cursor, competition_participation, sp):
        return StatsGenerator._calculate_matchup_data(cursor, competition_participation, sp,
                    "bot_p.result = 'loss'")

    @staticmethod
    def _calculate_matchup_tie_count(cursor, competition_participation, sp):
        return StatsGenerator._calculate_matchup_data(cursor, competition_participation, sp,
                    "bot_p.result = 'tie'")

    @staticmethod
    def _calculate_matchup_crash_count(cursor, competition_participation, sp):
        return StatsGenerator._calculate_matchup_data(cursor, competition_participation, sp,
                    """bot_p.result = 'loss'
                    and bot_p.result_cause in ('crash', 'timeout', 'initialization_failure')""")

    @staticmethod
    def _calculate_map_data(cursor, map, sp, query):
        return StatsGenerator._run_single_column_query(cursor, """
                    select count(cm.id) as count
                    from core_match cm
                    inner join core_matchparticipation bot_p on cm.id = bot_p.match_id
                    inner join core_map map on cm.map_id = map.id
                    inner join core_round cr on cm.round_id = cr.id
                    inner join core_competition cs on cr.competition_id = cs.id
                    where cs.id = %s -- make sure it's part of the current competition
                    and map.id = %s
                    and bot_p.bot_id = %s
                    and """ + query, 
                    [sp.competition_id, map.id, sp.bot_id])

    @staticmethod
    def _calculate_map_count(cursor, map, sp):
        return StatsGenerator._calculate_map_data(cursor, map, sp, 
                    "bot_p.result is not null and bot_p.result != 'none'")

    @staticmethod
    def _calculate_map_win_count(cursor, map, sp):
        return StatsGenerator._calculate_map_data(cursor,map, sp, 
                    "bot_p.result = 'win'")

    @staticmethod
    def _calculate_map_loss_count(cursor, map, sp):
        return StatsGenerator._calculate_map_data(cursor,map, sp,
                    "bot_p.result = 'loss'")

    @staticmethod
    def _calculate_map_tie_count(cursor, map, sp):
        return StatsGenerator._calculate_map_data(cursor,map, sp,
                    "bot_p.result = 'tie'")

    @staticmethod
    def _calculate_map_crash_count(cursor, map, sp):
        return StatsGenerator._calculate_map_data(cursor,map, sp,
                    """bot_p.result = 'loss'
                    and bot_p.result_cause in ('crash', 'timeout', 'initialization_failure')""")

    @staticmethod
    def _get_data(bot_id, competition_id):
        # this does not distinct between competitions
        with connection.cursor() as cursor:
            query = (f"""
                select 
                    cb.name, 
                    cp.resultant_elo as elo, 
                    cr.created as date
                from core_matchparticipation cp
                    inner join core_result cr on cp.match_id = cr.match_id
                    left join core_bot cb on cp.bot_id = cb.id
                    left join core_match cm on cp.match_id = cm.id
                    left join core_round crnd on cm.round_id = crnd.id
                    left join core_competition cc on crnd.competition_id = cc.id
                where resultant_elo is not null 
                    and bot_id = {bot_id} 
                    and competition_id = {competition_id}
                order by cr.created
                """)
            cursor.execute(query)
            elo_over_time = pd.DataFrame(cursor.fetchall())

        earliest_result_datetime = StatsGenerator.get_earliest_result_datetime(bot_id, competition_id)
        return elo_over_time, earliest_result_datetime

    @staticmethod
    def get_earliest_result_datetime(bot_id, competition_id):
        with connection.cursor() as cursor:
            query = (f"""
                select 
                    MIN(cr.created) as date
                from core_matchparticipation cp
                    inner join core_result cr on cp.match_id = cr.match_id
                    left join core_bot cb on cp.bot_id = cb.id
                    left join core_match cm on cp.match_id = cm.id
                    left join core_round crnd on cm.round_id = crnd.id
                    left join core_competition cc on crnd.competition_id = cc.id
                where resultant_elo is not null 
                    and bot_id = {bot_id} 
                    and competition_id = {competition_id}
                order by cr.created
                """)
            cursor.execute(query)
            return cursor.fetchall()

    @staticmethod
    def _generate_plot_images(df, update_date: datetime):
        plot1 = io.BytesIO()
        plot2 = io.BytesIO()

        legend = []

        fig, ax1 = plt.subplots(1, 1, figsize=(12, 9), sharex='all', sharey='all')
        ax1.plot(df["Date"], df['ELO'], color='#86c232')
        # ax.plot(df["Date"], df['ELO'], color='#86c232')
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)
        ax1.spines["left"].set_color('#86c232')
        ax1.spines["bottom"].set_color('#86c232')
        ax1.autoscale(enable=True, axis='x')
        ax1.get_xaxis().tick_bottom()
        ax1.get_yaxis().tick_left()
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b-%d'))
        ax1.tick_params(axis='x', colors='#86c232', labelsize=16)
        ax1.tick_params(axis='y', colors='#86c232', labelsize=16)
        # if update_date:

        legend.append('ELO')
        ax1.legend(legend, loc='lower center', fontsize='xx-large')

        plt.title('ELO over time', fontsize=20, color=('#86c232'))
        plt.tight_layout()  # Avoids savefig cutting off x-label
        plt.savefig(plot1, format="png", transparent=True)

        ax1.vlines([update_date],
                   min(df['ELO']), max(df['ELO']), colors='r', linestyles='--')
        legend.append('Last bot update')
        ax1.legend(legend, loc='lower center', fontsize='xx-large')
        plt.savefig(plot2, format="png", transparent=True)
        plt.close(fig)
        return plot1, plot2

    @staticmethod
    def _generate_elo_graph(bot_id: int, competition_id: int):
        df, update_date = StatsGenerator._get_data(bot_id, competition_id)
        if not df.empty:
            df.columns = ['Name', 'ELO', 'Date']

            # if the bot was updated more recently than the first result datetime, then use the bot updated date
            update_date = utc.localize(update_date[0][0])  # convert from a tuple
            bot_updated_datetime = Bot.objects.get(id=bot_id).bot_zip_updated
            if bot_updated_datetime > update_date:
                update_date = bot_updated_datetime

            return StatsGenerator._generate_plot_images(df, update_date)
        else:
            return None
