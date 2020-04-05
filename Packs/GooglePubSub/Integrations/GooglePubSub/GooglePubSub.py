from typing import Tuple

import demistomock as demisto
from CommonServerPython import *  # noqa: E402 lgtm [py/polluting-import]
from CommonServerUserPython import *  # noqa: E402 lgtm [py/polluting-import]

# IMPORTS
import httplib2
import urllib.parse
from oauth2client import service_account
from googleapiclient.discovery import build

import json
import requests
import dateparser

# Disable insecure warnings
requests.packages.urllib3.disable_warnings()

# CONSTANTS
RFC3339_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
DEMISTO_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'
SERVICE_NAME = 'pubsub'
SERVICE_VERSION = 'v1'
SCOPES = ['https://www.googleapis.com/auth/cloud-platform']

''' HELPER FUNCTIONS '''


class GoogleClient:
    """
    A Client class to wrap the google cloud api library.
    """

    def __init__(self, service_name, service_version, client_secret, scopes, proxy):
        credentials = service_account.ServiceAccountCredentials.from_json_keyfile_dict(client_secret, scopes)
        if proxy:
            http_client = credentials.authorize(self.get_http_client_with_proxy())
            self.service = build(service_name, service_version, http=http_client, credentials=credentials)
        else:
            self.service = build(service_name, service_version, credentials=credentials)

    # disable-secrets-detection-start
    @staticmethod
    def get_http_client_with_proxy():
        proxies = handle_proxy()
        if not proxies or not proxies['https']:
            raise Exception('https proxy value is empty. Check Demisto server configuration')
        https_proxy = proxies['https']
        if not https_proxy.startswith('https') and not https_proxy.startswith('http'):
            https_proxy = 'https://' + https_proxy
        parsed_proxy = urllib.parse.urlparse(https_proxy)
        proxy_info = httplib2.ProxyInfo(
            proxy_type=httplib2.socks.PROXY_TYPE_HTTP,
            proxy_host=parsed_proxy.hostname,
            proxy_port=parsed_proxy.port,
            proxy_user=parsed_proxy.username,
            proxy_pass=parsed_proxy.password)
        return httplib2.Http(proxy_info=proxy_info)
    # disable-secrets-detection-end


def init_google_client(params) -> GoogleClient:
    # insecure = not params.get('insecure')
    proxy = params.get('proxy')
    try:
        service_account_json = json.loads(params.get('service_account_json'))
    except ValueError:
        return_error(
            'Failed to parse Service Account Private Key in json format, please make sure you entered it correctly')
    client = GoogleClient(SERVICE_NAME, SERVICE_VERSION, service_account_json, SCOPES, proxy)
    return client


''' COMMAND FUNCTIONS '''


def test_module(client: GoogleClient):
    """
    Returning 'ok' indicates that the integration works like it is supposed to. Connection to the service is successful.
    :param client: GoogleClient
    :return: 'ok' if test passed, anything else will fail the test.
    """
    return 'ok', {}


def topics_list_command(client: GoogleClient, project_name: str, page_size: str = None, page_token: str = None) -> \
        Tuple[str, dict, dict]:
    """
    Get topics list by project_name
    Requires one of the following OAuth scopes:

        https://www.googleapis.com/auth/pubsub
        https://www.googleapis.com/auth/cloud-platform

    :param client: GoogleClient
    :param project_name: project name
    :param page_size: page size
    :param page_token: page token, as returned from the api
    :return: list of topics
    """
    topics_list = client.service.projects().topics().list(project=project_name, pageSize=page_size,
                                                          pageToken=page_token).execute()

    # readable output will be in markdown format - https://www.markdownguide.org/basic-syntax/
    readable_output = tableToMarkdown(f'Topics for project {project_name}', topics_list)
    outputs = {
        'GoogleCloudPubSub.Topics': {project_name: topics_list}
    }
    return (
        readable_output,
        outputs,
        topics_list  # raw response - the original response
    )


def publish_message_command(client: GoogleClient, topic_name: str = None, message_data: str = None,
                            message_attributes: str = None) -> Tuple[str, dict, dict]:
    """
    Publishes message in the topic
    Requires one of the following OAuth scopes:

        https://www.googleapis.com/auth/pubsub
        https://www.googleapis.com/auth/cloud-platform

    :param message_attributes: message attributes separated by key=val pairs sepearated by ','
    :param message_data: message data str
    :param topic_name: topic name with project name prefix
    :param client: GoogleClient
    :return: list of topics
    """
    body = get_publish_body(message_attributes, message_data)
    published_messages = client.service.projects().topics().publish(
        topic=topic_name,
        body=body
    ).execute()

    output = []
    for msg_id in published_messages["messageIds"]:
        output.append({"topic": topic_name, "messageId": msg_id})

    ec = {'GoogleCloudPubSub.PublishedMessages(val.messageId === obj.messageId)': output}
    return (
        tableToMarkdown('Google Cloud PubSub Published Messages', published_messages, removeNull=True),
        ec,
        published_messages
    )


def get_publish_body(message_attributes, message_data):
    """
    Creates publish messages body from given arguments
    :param message_attributes: message attributes
    :param message_data: message data
    :return: publish message body
    """
    message = {}
    if message_data:
        # convert to base64 string
        message['data'] = str(base64.b64encode(message_data.encode('utf8')))[2:-1]
    if message_attributes:
        message['attributes'] = attribute_pairs_to_dict(message_attributes)
    body = {'messages': [message]}
    return body


def attribute_pairs_to_dict(attrs_str: str, delim_char: str = ';'):
    """
    Transforms a string of multiple inputs to a dictionary list

    :param attrs_str: attributes separated by key=val pairs sepearated by ','
    :param delim_char: delimiter character between atrribute pairs
    :return:
    """
    attrs = {}
    regex = re.compile(r'(.*)=(.*)')
    for f in attrs_str.split(delim_char):
        match = regex.match(f)
        if match is None:
            raise ValueError(f'Could not parse field: {f}')

        attrs.update({match.group(1): match.group(2)})

    return attrs


def fetch_incidents(client, last_run, first_fetch_time):
    """
    This function will execute each interval (default is 1 minute).

    Args:
        client (Client): HelloWorld client
        last_run (dateparser.time): The greatest incident created_time we fetched from last fetch
        first_fetch_time (dateparser.time): If last_run is None then fetch all incidents since first_fetch_time

    Returns:
        next_run: This will be last_run in the next fetch-incidents
        incidents: Incidents that will be created in Demisto
    """
    # Get the last fetch time, if exists
    last_fetch = last_run.get('last_fetch')

    # Handle first time fetch
    if last_fetch is None:
        last_fetch, _ = dateparser.parse(first_fetch_time)
    else:
        last_fetch = dateparser.parse(last_fetch)

    latest_created_time = last_fetch
    incidents = []
    items = client.list_incidents()
    for item in items:
        incident_created_time = dateparser.parse(item['created_time'])
        incident = {
            'name': item['description'],
            'occurred': incident_created_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'rawJSON': json.dumps(item)
        }

        incidents.append(incident)

        # Update last run and add incident if the incident is newer than last fetch
        if incident_created_time > latest_created_time:
            latest_created_time = incident_created_time

    next_run = {'last_fetch': latest_created_time.strftime(DEMISTO_DATETIME_FORMAT)}
    return next_run, incidents


def main():
    params = demisto.params()
    client = init_google_client(params)
    command = demisto.command()
    LOG(f'Command being called is {command}')
    try:
        if command == 'fetch-incidents':
            # Set and define the fetch incidents command to run after activated via integration settings.
            first_fetch_time = params.get('fetch_time', '3 days').strip()
            next_run, incidents = fetch_incidents(
                client=client,
                last_run=demisto.getLastRun(),
                first_fetch_time=first_fetch_time)

            demisto.setLastRun(next_run)
            demisto.incidents(incidents)
        else:
            args = demisto.args()
            commands = {
                'test-module': test_module,
                'google-cloud-pubsub-topics-list': topics_list_command,
                'google-cloud-pubsub-topic-publish-message': publish_message_command,
            }
            return_outputs(*commands[command](client, **args))  # type: ignore[operator]

    # Log exceptions
    except Exception as e:
        return_error(f'Failed to execute {demisto.command()} command. Error: {str(e)}')


if __name__ in ('__main__', '__builtin__', 'builtins'):
    main()
