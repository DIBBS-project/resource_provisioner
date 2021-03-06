#!/usr/bin/env python
"""
Test the Django service
"""
import base64
import json
import pathlib
import sys
import textwrap
import time

import requests

from common_dibbs.names import AUTHORIZATION_HEADER

from sham_ar import app as sham_ar
from sham_cas import app as sham_cas
from helpers import FlaskAppManager


TEST_DIR = pathlib.Path(__file__).resolve().parent
BASE_DIR = TEST_DIR.parent

ROOT = 'http://localhost:8002'
CAS_URL = 'http://localhost:7000'
AR_URL = 'http://localhost:8003'

ALICE_VALID = {AUTHORIZATION_HEADER: 'alice,1'}
ALICE_INVALID = {AUTHORIZATION_HEADER: 'alice,0'}


def obfuscate(data):
    return base64.b64encode(json.dumps(data).encode('utf-8')).decode('utf-8')


def assertStatus(response, expected, message=None):
    try:
        start, stop = expected
    except TypeError:
        if response.status_code == expected:
            return
    else:
        if start <= response.status_code < stop:
            return
        expected = '[{}, {})'.format(start, stop)

    if message:
        print(message, file=sys.stderr)

    print('Received status {}, expected {}\n-------------\n{}'
        .format(response.status_code, expected, response.content),
        file=sys.stderr)

    raise AssertionError(message or "bad status code")


def test(ar=None, cas=None):
    ar_apps = ar.app.config.apps = {}
    ar_imps = ar.app.config.imps = {}
    ar_sites = ar.app.config.sites = {}
    # sanity check root
    response = requests.get(ROOT)
    assertStatus(response, 200)

    # # check with auth
    # response = requests.get(ROOT, headers=ALICE_VALID)
    # assertStatus(response, 200)

    # load fake site
    SITE = 'some-site-id'
    CRED_B64JSON = obfuscate({'username': 'magic', 'password': 'johnson', 'project_name': 'spartans'})
    ar_sites[SITE] = {'api_url': 'http://localhost:44000/v3'}

    print('* TEST: refuse unauthed credential create')
    response = requests.post(ROOT + '/credentials/', json={
        'site': SITE,
        'name': 'me@site',
        'credentials': CRED_B64JSON,
    })
    assertStatus(response, 403, 'auth required')

    print('* TEST: create credential')
    response = requests.post(ROOT + '/credentials/', headers=ALICE_VALID, json={
        'site': SITE,
        'name': 'me@site',
        'credentials': CRED_B64JSON,
    })
    assertStatus(response, 201)
    credentials = response.json()
    assert all(key in credentials for key in ['id', 'created', 'site', 'user'])
    assert not any(key in credentials for key in ['credentials'])
    cred_id = credentials['id']

    # - site must exist
    print('* TEST: refuse create credential site missing')
    response = requests.post(ROOT + '/credentials/', headers=ALICE_VALID, json={
        'site': 'non-existant',
        'name': 'me@site2',
        'credentials': CRED_B64JSON,
    })
    assertStatus(response, (400, 500), 'should error on nonexistant site')

    print('* TEST: list credentials')
    response = requests.get(ROOT + '/credentials/')
    assertStatus(response, 200)
    all_credentials = response.json()
    assert len(all_credentials) == 1

    # make sure it's a black hole for the user (can't get back plaintext or raw hash)
    print('* TEST: write-only credential data')
    response = requests.get(ROOT + '/credentials/{}/'.format(cred_id))
    assertStatus(response, 200)
    credentials = response.json()
    assert 'credentials' not in credentials

    # fake implementation in flask
    IMPL = 'some-impl-id'
    ar_imps[IMPL] = {
        'site': SITE,
        'appliance': 'magic',
        'script': textwrap.dedent('''\
            heat_template_version: 2014-04-04
            script: something
        '''),
        'script_parsed': json.dumps({
            'heat_template_version': '2014-04-04',
            'script': 'something',
        }),
    }

    print('* TEST: create cluster, refuse if missing implementation')
    response = requests.post(ROOT + '/clusters/', headers=ALICE_VALID, json={
        'credential': cred_id,
    })
    assertStatus(response, 400)

    # post cluster
    print('* TEST: create cluster')
    response = requests.post(ROOT + '/clusters/', headers=ALICE_VALID, json={
        'credential': cred_id,
        'implementation': IMPL,
    })
    assertStatus(response, 201)

    # credential must exist
    print('* TEST: create cluster, credential must exist')
    response = requests.post(ROOT + '/clusters/', headers=ALICE_VALID, json={
        'credential': 'garbage',
        'implementation': IMPL,
    })
    assertStatus(response, (400, 500), 'should error on nonnexistant credential')

    # implementation must exist
    print('* TEST: create cluster, implementation must exist')
    response = requests.post(ROOT + '/clusters/', headers=ALICE_VALID, json={
        'credential': cred_id,
        'implementation': 'non-existant',
    })
    assertStatus(response, (400, 500), 'should error on nonnexistant implementation')
    assert all(word in response.text.lower() for word in ['implementation', 'found'])

    # implementation site must match credential
    print('* TEST: create cluster, implementation site must match credential site')
    IMPL2 = 'some-other-impl-id'
    ar_imps[IMPL2] = {'site': 'other-site', 'appliance': 'magic'}
    response = requests.post(ROOT + '/clusters/', headers=ALICE_VALID, json={
        'credential': cred_id,
        'implementation': IMPL2,
    })
    assertStatus(response, (400, 500), 'should error on clashing implementation site, credential site')
    assert all(word in response.text.lower() for word in ['match', 'site'])


def self_test():
    requests.get(CAS_URL + '/auth/tokens', headers=ALICE_INVALID)
    requests.get(AR_URL)


def main(argv=None):
    with FlaskAppManager(sham_cas, port=7000) as cas, \
            FlaskAppManager(sham_ar, port=8003) as ar:
        self_test()
        return test(ar=ar, cas=cas)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
