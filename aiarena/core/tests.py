import os

from django.core.files import File
from django.test import TestCase

from aiarena.core.models import User, Bot, Map
from aiarena.core.utils import calculate_md5


class BaseTestCase(TestCase):
    # For some reason using an absolute file path here will cause it to mangle the save directory and fail
    # later whilst handling the bot_zip file save
    test_bot_zip_path = 'aiarena/core/test_bot.zip'
    # test_bot1_data_path = os.path.join(BASE_DIR, 'aiarena/core/test_bot1_data.zip')
    # test_bot2_data_path = os.path.join(BASE_DIR, 'aiarena/core/test_bot1_data.zip')
    test_bot1_data_path = 'aiarena/core/test_bot1_data.zip'
    test_bot2_data_path = 'aiarena/core/test_bot2_data.zip'

    def _create_map(self, name):
        return Map.objects.create(name=name)

    def _create_bot(self, user, name):
        with open(self.test_bot_zip_path, 'rb') as bot_zip:
            return Bot.objects.create(user=user, name=name, bot_zip=File(bot_zip))

    def _create_active_bot(self, user, name):
        with open(self.test_bot_zip_path, 'rb') as bot_zip:
            return Bot.objects.create(user=user, name=name, bot_zip=File(bot_zip), active=True)

    def _post_to_matches(self):
        return self.client.post('/api/arenaclient/matches/')

    def _post_to_results(self, match_id, result_type):
        filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testReplay.SC2Replay')
        with open(filename) as replayFile, open(self.test_bot1_data_path) as bot1_data, open(
                self.test_bot2_data_path) as bot2_data:
            return self.client.post('/api/arenaclient/results/',
                                    {'match': match_id,
                                     'type': result_type,
                                     'replay_file': replayFile,
                                     'duration': 500,
                                     'bot1_data': bot1_data,
                                     'bot2_data': bot2_data})

    def _post_to_results_no_bot_datas(self, match_id, result_type):
        filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testReplay.SC2Replay')
        with open(filename) as replayFile:
            return self.client.post('/api/arenaclient/results/',
                                    {'match': match_id,
                                     'type': result_type,
                                     'replay_file': replayFile,
                                     'duration': 500})

    def _post_to_results_no_bot1_data(self, match_id, result_type):
        filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testReplay.SC2Replay')
        with open(filename) as replayFile, open(self.test_bot1_data_path) as bot2_data:
            return self.client.post('/api/arenaclient/results/',
                                    {'match': match_id,
                                     'type': result_type,
                                     'replay_file': replayFile,
                                     'duration': 500,
                                     'bot2_data': bot2_data})

    def _post_to_results_no_bot2_data(self, match_id, result_type):
        filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testReplay.SC2Replay')
        with open(filename) as replayFile, open(self.test_bot1_data_path) as bot1_data:
            return self.client.post('/api/arenaclient/results/',
                                    {'match': match_id,
                                     'type': result_type,
                                     'replay_file': replayFile,
                                     'duration': 500,
                                     'bot1_data': bot1_data})

    def _post_to_results_no_replay(self, match_id, result_type):
        return self.client.post('/api/arenaclient/results/',
                                {'match': match_id,
                                 'type': result_type,
                                 'replay_file': '',
                                 'duration': 500})


class LoggedInTestCase(BaseTestCase):
    def setUp(self):
        super(LoggedInTestCase, self).setUp()

        self.staffUser1 = User.objects.create_user(username='staff_user', password='x', email='staff_user@aiarena.net',
                                                   is_staff=True)
        self.regularUser1 = User.objects.create_user(username='regular_user1', password='x',
                                                     email='regular_user1@aiarena.net')


class MatchReadyTestCase(LoggedInTestCase):
    def setUp(self):
        super(MatchReadyTestCase, self).setUp()

        self.regularUserBot1 = self._create_bot(self.regularUser1, 'regularUserBot1')
        self.regularUserBot2 = self._create_bot(self.regularUser1, 'regularUserBot2')
        self.staffUserBot1 = self._create_bot(self.staffUser1, 'staffUserBot1')
        self.staffUserBot2 = self._create_bot(self.staffUser1, 'staffUserBot2')
        self._create_map('testmap1')


# User this to pre-build a full dataset for testing
class FullDataSetTestCase(MatchReadyTestCase):

    def setUp(self):
        super(FullDataSetTestCase, self).setUp()
        self.client.login(username='staff_user', password='x')

        self._create_map('testmap2')
        self._generate_extra_users()
        self._generate_extra_bots()

        self._generate_match_activity()
        self.client.logout()  # child tests can login if they require

    def _generate_match(self, result_type):
        response = self._post_to_matches()
        self.assertEqual(response.status_code, 201)
        response = self._post_to_results(response.data['id'], result_type)
        self.assertEqual(response.status_code, 201)

    def _generate_match_activity(self):
        self._generate_match('InitializationError')
        self._generate_match('Timeout')
        self._generate_match('Player1Win')
        self._generate_match('Player1Crash')
        self._generate_match('Player1TimeOut')
        self._generate_match('Player2Win')
        self._generate_match('Player2Crash')
        self._generate_match('Player2TimeOut')
        self._generate_match('Tie')
        self._generate_match('Error')

    def _generate_extra_bots(self):
        self.regularUser1Bot1 = self._create_active_bot(self.regularUser1, 'regularUser1Bot1')
        self.regularUser1Bot2 = self._create_active_bot(self.regularUser1, 'regularUser1Bot2')
        self.regularUser2Bot1 = self._create_bot(self.regularUser2, 'regularUser2Bot1')
        self.regularUser2Bot2 = self._create_active_bot(self.regularUser2, 'regularUser2Bot2')
        self.regularUser3Bot1 = self._create_active_bot(self.regularUser3, 'regularUser3Bot1')
        self.regularUser3Bot2 = self._create_active_bot(self.regularUser3, 'regularUser3Bot2')
        self.regularUser4Bot1 = self._create_bot(self.regularUser4, 'regularUser4Bot1')
        self.regularUser4Bot2 = self._create_bot(self.regularUser4, 'regularUser4Bot2')

    def _generate_extra_users(self):
        self.regularUser2 = User.objects.create_user(username='regular_user2', password='x',
                                                     email='regular_user2@aiarena.net')
        self.regularUser3 = User.objects.create_user(username='regular_user3', password='x',
                                                     email='regular_user3@aiarena.net')
        self.regularUser4 = User.objects.create_user(username='regular_user4', password='x',
                                                     email='regular_user4@aiarena.net')


class UtilsTestCase(BaseTestCase):
    def test_calc_md5(self):
        filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'test_bot.zip')
        file = open(filename, 'rb')
        self.assertEqual('7411028ba931baaad47bf5810215e4f8', calculate_md5(filename))


class UserTestCase(BaseTestCase):
    def test_user_creation(self):
        User.objects.create(username='test user', email='test@test.com')


class BotTestCase(BaseTestCase):
    def test_bot_creation(self):
        user = User.objects.create(username='test user', email='test@test.com')

        with open(self.test_bot_zip_path, 'rb') as bot_zip:
            bot = Bot.objects.create(user=user, name='test', bot_zip=File(bot_zip), plays_race='T', type='Python')
        self.assertEqual('7411028ba931baaad47bf5810215e4f8', bot.bot_zip_md5hash)

        # check the bot file now exists
        self.assertTrue(os.path.isfile('./private-media/bots/{0}/bot_zip'.format(bot.id)))

        # todo: check file overwrite functionality


class PageRenderTestCase(FullDataSetTestCase):
    """
    Tests to ensure website pages don't break.
    """

    def test_get_index_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_get_bots_page(self):
        response = self.client.get('/bots/')
        self.assertEqual(response.status_code, 200)

    def test_get_bot_page(self):
        response = self.client.get('/bots/{0}/'.format(self.regularUserBot1.id))
        self.assertEqual(response.status_code, 200)

    def test_get_author_page(self):
        response = self.client.get('/authors/')
        self.assertEqual(response.status_code, 200)

    def test_get_authors_page(self):
        response = self.client.get('/authors/{0}/'.format(self.regularUser1.id))
        self.assertEqual(response.status_code, 200)

    def test_get_ranking_page(self):
        response = self.client.get('/ranking/')
        self.assertEqual(response.status_code, 200)

    def test_get_results_page(self):
        response = self.client.get('/results/')
        self.assertEqual(response.status_code, 200)

    def test_get_rules_page(self):
        response = self.client.get('/rules/')
        self.assertEqual(response.status_code, 200)

    def test_get_login_page(self):
        response = self.client.get('/accounts/login/')
        self.assertEqual(response.status_code, 200)

    def test_get_register_page(self):
        response = self.client.get('/accounts/register/')
        self.assertEqual(response.status_code, 200)

    def test_get_reset_password_page(self):
        response = self.client.get('/accounts/password_reset/')
        self.assertEqual(response.status_code, 200)


class PrivateStorageTestCase(MatchReadyTestCase):
    pass  # todo
