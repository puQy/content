import unittest
import demisto_client
from unittest import mock
from Tests.test_content import ParallelPrintsManager
from Tests.Marketplace.search_and_install_packs import search_and_install_packs_and_their_dependencies

BASE_URL = 'http://123-fake-api.com'
API_KEY = 'test-api-key'

MOCK_PACKS_SEARCH_RESULTS = """{
    "packs": [
        {
            "id": "HelloWorld",
            "currentVersion": "2.0.0",
            "name": "HelloWorld",
            "dependencies": {"Base": {}, "TestPack": {}}
        },
        {
            "id": "TestPack",
            "currentVersion": "1.0.0",
            "name": "TestPack",
            "dependencies": {"Base": {}}
        },
        {
            "id": "AzureSentinel",
            "currentVersion": "1.0.0",
            "name": "AzureSentinel",
            "dependencies": {"Base": {}}
        },
        {
            "id": "Base",
            "currentVersion": "1.0.0",
            "name": "Base",
            "dependencies": {}
        }
    ]
}"""

MOCK_PACKS_INSTALLATION_RESULT = """[
    {
        "id": "HelloWorld",
        "currentVersion": "2.0.0",
        "name": "HelloWorldPremium",
        "installed": "2020-04-06T16:35:10.998538+03:00"
    },
    {
        "id": "TestPack",
        "currentVersion": "1.0.0",
        "name": "TestPack",
        "installed": "2020-04-13T16:43:22.304144+03:00"
    },
    {
        "id": "AzureSentinel",
        "currentVersion": "1.0.0",
        "name": "AzureSentinel",
        "installed": "2020-04-13T16:57:32.655598+03:00"
    },
    {
        "id": "Base",
        "currentVersion": "1.0.0",
        "name": "Base",
        "installed": "2020-04-06T14:54:09.755811+03:00"
    }
]"""


def mocked_request(*args, **kwargs):
    if kwargs['path'] == '/contentpacks/marketplace/search':
        return MOCK_PACKS_SEARCH_RESULTS, 200, None
    elif kwargs['path'] == '/contentpacks/marketplace/install':
        return MOCK_PACKS_INSTALLATION_RESULT, 200, None
    return None, None, None


class MockConfiguration:
    def __init__(self):
        self.host = None


class MockApiClient:
    def __init__(self):
        self.configuration = MockConfiguration()


class MockClient:
    def __init__(self):
        self.api_client = MockApiClient()


class TestSearchAndInstallPacks(unittest.TestCase):
    @mock.patch('demisto_client.generic_request_func', side_effect=mocked_request)
    def test_search_and_install_packs_and_their_dependencies(self, mocker):
        good_integrations_files = [
            'Packs/HelloWorld/Integrations/HelloWorld/HelloWorld.yml',
            'Packs/AzureSentinel/Integrations/AzureSentinel/AzureSentinel.yml'
        ]

        bad_integrations_files = ['malformed_integration_file']

        mocker.patch.object(demisto_client, 'configure', return_value=MockClient())
        client = demisto_client.configure(base_url=BASE_URL, api_key=API_KEY)
        prints_manager = ParallelPrintsManager(1)

        installed_packs = search_and_install_packs_and_their_dependencies(good_integrations_files,
                                                                          client,
                                                                          prints_manager)
        assert 'HelloWorld' in installed_packs
        assert 'AzureSentinel' in installed_packs
        assert 'TestPack' in installed_packs
        assert 'Base' in installed_packs
        assert len(installed_packs) == 4

        installed_packs = search_and_install_packs_and_their_dependencies(bad_integrations_files,
                                                                          client,
                                                                          prints_manager)
        assert len(installed_packs) == 0
