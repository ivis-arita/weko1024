# -*- coding: utf-8 -*-
#
# Copyright (C) 2020 National Institute of Informatics.
#
# INVENIO-ResourceSyncServer is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more
# details.

"""Pytest configuration.

See https://pytest-invenio.readthedocs.io/ for documentation on which test
fixtures are available.
"""

from __future__ import absolute_import, print_function

import os
import shutil
import tempfile
import json
import uuid
import copy
import requests
from os.path import join
from datetime import date, datetime, timedelta
from time import sleep
import pytest
from mock import Mock, patch
from pytest_mock import mocker
from flask import Flask, url_for
from flask_babelex import Babel, lazy_gettext as _
from flask_celeryext import FlaskCeleryExt
from flask_menu import Menu
from flask_login import current_user, login_user, LoginManager
from werkzeug.local import LocalProxy
from tests.helpers import create_record, json_data
from six import BytesIO
from elasticsearch import Elasticsearch
from simplekv.memory.redisstore import RedisStore
# from moto import mock_s3

from invenio_deposit.config import (
    DEPOSIT_DEFAULT_STORAGE_CLASS,
    DEPOSIT_RECORDS_UI_ENDPOINTS,
    DEPOSIT_REST_ENDPOINTS,
    DEPOSIT_DEFAULT_JSONSCHEMA,
    DEPOSIT_JSONSCHEMAS_PREFIX,
)
from invenio_stats.contrib.event_builders import (
    build_file_unique_id,
    build_record_unique_id,
    file_download_event_builder
)
from invenio_accounts import InvenioAccounts
from invenio_accounts.models import User, Role
from invenio_accounts.testutils import create_test_user, login_user_via_session
from invenio_access.models import ActionUsers
from invenio_access import InvenioAccess
from invenio_access.models import ActionUsers, ActionRoles
from invenio_assets import InvenioAssets
from invenio_cache import InvenioCache
from invenio_communities import InvenioCommunities
from invenio_db import InvenioDB
from invenio_db import db as db_
from invenio_files_rest.models import Location
from invenio_i18n import InvenioI18N
from invenio_indexer import InvenioIndexer
from invenio_jsonschemas import InvenioJSONSchemas
from invenio_mail import InvenioMail
from invenio_oaiserver import InvenioOAIServer
from invenio_oaiserver.models import OAISet
from invenio_pidrelations import InvenioPIDRelations
from invenio_records import InvenioRecords
from invenio_search import InvenioSearch
from invenio_stats.config import SEARCH_INDEX_PREFIX as index_prefix
from invenio_oaiharvester.models import HarvestSettings
from invenio_stats import InvenioStats
from invenio_admin import InvenioAdmin
from invenio_search import RecordsSearch
from invenio_pidstore import InvenioPIDStore, current_pidstore
from invenio_records_rest.utils import PIDConverter
from invenio_records.models import RecordMetadata
from invenio_deposit.api import Deposit
from invenio_communities.models import Community
from invenio_search import current_search_client, current_search
from invenio_queues.proxies import current_queues
from invenio_files_rest.permissions import bucket_listmultiparts_all, \
    bucket_read_all, bucket_read_versions_all, bucket_update_all, \
    location_update_all, multipart_delete_all, multipart_read_all, \
    object_delete_all, object_delete_version_all, object_read_all, \
    object_read_version_all
from invenio_files_rest.models import Bucket, Location, ObjectVersion
from invenio_db.utils import drop_alembic_version_table
from invenio_records_rest.config import RECORDS_REST_SORT_OPTIONS
from invenio_pidstore.models import PersistentIdentifier, PIDStatus, Redirect
from invenio_pidrelations.models import PIDRelation
from invenio_oaiserver.models import Identify
from invenio_pidstore.providers.recordid import RecordIdProvider
from invenio_records_rest import InvenioRecordsREST, config
from invenio_records_rest.facets import terms_filter
from invenio_rest import InvenioREST
from invenio_records_rest.views import create_blueprint_from_app

from weko_deposit.config import WEKO_BUCKET_QUOTA_SIZE, WEKO_MAX_FILE_SIZE
from weko_admin.models import FacetSearchSetting
from weko_schema_ui.models import OAIServerSchema
from weko_index_tree.api import Indexes
from weko_records import WekoRecords
from weko_records.api import ItemTypes, ItemsMetadata, WekoRecord, Mapping
from weko_records.config import WEKO_ITEMTYPE_EXCLUDED_KEYS
from weko_records.models import ItemType, ItemTypeMapping, ItemTypeName
from weko_records_ui.models import PDFCoverPageSettings
from weko_records_ui.config import WEKO_PERMISSION_SUPER_ROLE_USER, WEKO_PERMISSION_ROLE_COMMUNITY, EMAIL_DISPLAY_FLG,WEKO_RECORDS_UI_BULK_UPDATE_FIELDS
from weko_groups import WekoGroups
from weko_admin import WekoAdmin
from weko_workflow import WekoWorkflow
from weko_workflow.models import (
    Action,
    ActionStatus,
    ActionStatusPolicy,
    Activity,
    FlowAction,
    FlowDefine,
    WorkFlow
)
from weko_theme import WekoTheme
from weko_theme.views import blueprint as weko_theme_blueprint
from weko_theme.config import THEME_BODY_TEMPLATE,WEKO_THEME_ADMIN_ITEM_MANAGEMENT_INIT_TEMPLATE
from invenio_communities.views.ui import blueprint as invenio_communities_blueprint
from weko_index_tree.models import Index
from weko_index_tree import WekoIndexTree, WekoIndexTreeREST
from weko_search_ui.views import blueprint_api
from weko_search_ui.rest import create_blueprint
from weko_search_ui import WekoSearchUI, WekoSearchREST
from weko_search_ui.config import SEARCH_UI_SEARCH_INDEX, WEKO_SEARCH_TYPE_DICT,WEKO_SEARCH_UI_BASE_TEMPLATE
from weko_redis.redis import RedisConnection
from weko_admin.models import SessionLifetime
from weko_admin.config import WEKO_ADMIN_MANAGEMENT_OPTIONS, WEKO_ADMIN_DEFAULT_ITEM_EXPORT_SETTINGS
from weko_index_tree.models import IndexStyle
from weko_deposit.api import WekoDeposit, WekoRecord, WekoIndexer

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy import event
from sqlalchemy_utils.functions import create_database, database_exists, drop_database


@pytest.fixture(scope='module')
def celery_config():
    """Override pytest-invenio fixture.

    TODO: Remove this fixture if you add Celery support.
    """
    return {}


@pytest.fixture(scope='module')
def create_app(instance_path):
    """Application factory fixture."""
    def factory(**config):
        app = Flask('testapp', instance_path=instance_path)
        app.config.update(**config)
        Babel(app)
        InvenioResourceSyncServer(app)
        app.register_blueprint(blueprint)
        return app
    return factory


@pytest.yield_fixture(scope='session')
def search_class():
    """Search class."""
    yield TestSearch


@pytest.yield_fixture()
def instance_path():
    """Temporary instance path."""
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)


@pytest.fixture()
def base_app(instance_path, request):
    """Flask application fixture."""
    app_ = Flask('testapp', instance_path=instance_path, static_folder=join(instance_path, "static"),)
    os.environ['INVENIO_WEB_HOST_NAME']="127.0.0.1"
    app_.config.update(
        ACCOUNTS_JWT_ENABLE=True,
        SECRET_KEY='SECRET_KEY',
        WEKO_INDEX_TREE_UPDATED=True,
        DEPOSIT_FILES_API = '/api/files',
        TESTING=True,
        WEKO_ROOT_INDEX=1,
        INVENIO_RESOURCESYNCSERVER_TMP_PREFIX="test",
        FILES_REST_DEFAULT_QUOTA_SIZE=None,
        FILES_REST_DEFAULT_STORAGE_CLASS='S',
        FILES_REST_STORAGE_CLASS_LIST={
            'S': 'Standard',
            'A': 'Archive',
        },
        CACHE_REDIS_URL='redis://redis:6379/0',
        CACHE_REDIS_DB='0',
        CACHE_REDIS_HOST="redis",
        WEKO_INDEX_TREE_STATE_PREFIX="index_tree_expand_state",
        REDIS_PORT='6379',
        DEPOSIT_DEFAULT_JSONSCHEMA=DEPOSIT_DEFAULT_JSONSCHEMA,
        SERVER_NAME='TEST_SERVER',
        LOGIN_DISABLED=False,
        INDEXER_DEFAULT_DOCTYPE='item-v1.0.0',
        INDEXER_FILE_DOC_TYPE='content',
        INDEXER_DEFAULT_INDEX="{}-weko-item-v1.0.0".format(
            'test'
        ),
        INDEX_IMG='indextree/36466818-image.jpg',
        # SQLALCHEMY_DATABASE_URI=os.getenv('SQLALCHEMY_DATABASE_URI',
        #                                   'postgresql+psycopg2://invenio:dbpass123@postgresql:5432/invenio'),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            'SQLALCHEMY_DATABASE_URI', 'sqlite:///test.db'),
        SEARCH_ELASTIC_HOSTS=os.environ.get(
            'SEARCH_ELASTIC_HOSTS', 'elasticsearch'),
        SQLALCHEMY_TRACK_MODIFICATIONS=True,
        JSONSCHEMAS_HOST='inveniosoftware.org',
        ACCOUNTS_USERINFO_HEADERS=True,
        I18N_LANGUAGES=[("ja", "Japanese"), ("en", "English")],
        WEKO_INDEX_TREE_INDEX_LOCK_KEY_PREFIX="lock_index_",
        WEKO_PERMISSION_SUPER_ROLE_USER=WEKO_PERMISSION_SUPER_ROLE_USER,
        WEKO_PERMISSION_ROLE_COMMUNITY=WEKO_PERMISSION_ROLE_COMMUNITY,
        EMAIL_DISPLAY_FLG=EMAIL_DISPLAY_FLG,
        THEME_SITEURL="https://localhost",
        DEPOSIT_RECORDS_UI_ENDPOINTS=DEPOSIT_RECORDS_UI_ENDPOINTS,
        DEPOSIT_REST_ENDPOINTS=DEPOSIT_REST_ENDPOINTS,
        DEPOSIT_DEFAULT_STORAGE_CLASS=DEPOSIT_DEFAULT_STORAGE_CLASS,
        # RECORDS_REST_SORT_OPTIONS=RECORDS_REST_SORT_OPTIONS,
        RECORDS_REST_DEFAULT_LOADERS = {
            'application/json': lambda: request.get_json(),
            'application/json-patch+json': lambda: request.get_json(force=True),
        },
        FILES_REST_OBJECT_KEY_MAX_LEN = 255,
        # SEARCH_UI_SEARCH_INDEX=SEARCH_UI_SEARCH_INDEX,
        SEARCH_UI_SEARCH_INDEX="test-weko",
        # SEARCH_ELASTIC_HOSTS=os.environ.get("INVENIO_ELASTICSEARCH_HOST"),
        SEARCH_INDEX_PREFIX="{}-".format('test'),
        SEARCH_CLIENT_CONFIG=dict(timeout=120, max_retries=10),
        OAISERVER_ID_PREFIX="oai:inveniosoftware.org:recid/",
        OAISERVER_RECORD_INDEX="_all",
        OAISERVER_REGISTER_SET_SIGNALS=True,
        OAISERVER_METADATA_FORMATS={
            "jpcoar_1.0": {
                "serializer": (
                    "weko_schema_ui.utils:dumps_oai_etree",
                    {
                        "schema_type": "jpcoar_v1",
                    },
                ),
                "namespace": "https://irdb.nii.ac.jp/schema/jpcoar/1.0/",
                "schema": "https://irdb.nii.ac.jp/schema/jpcoar/1.0/jpcoar_scm.xsd",
            }
        },
        THEME_SITENAME = 'WEKO3',
        IDENTIFIER_GRANT_SUFFIX_METHOD = 0,
        THEME_FRONTPAGE_TEMPLATE = 'weko_theme/frontpage.html',
        BASE_EDIT_TEMPLATE = 'weko_theme/edit.html',
        BASE_PAGE_TEMPLATE = 'weko_theme/page.html',
        RECORDS_REST_ENDPOINTS=copy.deepcopy(config.RECORDS_REST_ENDPOINTS),
        RECORDS_REST_DEFAULT_CREATE_PERMISSION_FACTORY=None,
        RECORDS_REST_DEFAULT_DELETE_PERMISSION_FACTORY=None,
        RECORDS_REST_DEFAULT_READ_PERMISSION_FACTORY=None,
        RECORDS_REST_DEFAULT_UPDATE_PERMISSION_FACTORY=None,
        RECORDS_REST_DEFAULT_RESULTS_SIZE=10,
        # RECORDS_REST_DEFAULT_SEARCH_INDEX=search_class.Meta.index,
        # RECORDS_REST_FACETS={
        #     search_class.Meta.index: {
        #         'aggs': {
        #             'stars': {'terms': {'field': 'stars'}}
        #         },
        #         'post_filters': {
        #             'stars': terms_filter('stars'),
        #         }
        #     }
        # },
        # RECORDS_REST_SORT_OPTIONS={
        #     search_class.Meta.index: dict(
        #         year=dict(
        #             fields=['year'],
        #         )
        #     )
        # },
        FILES_REST_DEFAULT_MAX_FILE_SIZE=None,
        WEKO_ADMIN_ENABLE_LOGIN_INSTRUCTIONS = False,
        WEKO_ADMIN_MANAGEMENT_OPTIONS=WEKO_ADMIN_MANAGEMENT_OPTIONS,
        WEKO_ADMIN_DEFAULT_ITEM_EXPORT_SETTINGS=WEKO_ADMIN_DEFAULT_ITEM_EXPORT_SETTINGS,
        WEKO_ADMIN_CACHE_TEMP_DIR_INFO_KEY_DEFAULT = 'cache::temp_dir_info',
        WEKO_ITEMS_UI_EXPORT_TMP_PREFIX = 'weko_export_',
        WEKO_SEARCH_UI_IMPORT_TMP_PREFIX = 'weko_import_',
        WEKO_AUTHORS_ES_INDEX_NAME = "{}-authors".format(index_prefix),
        WEKO_AUTHORS_ES_DOC_TYPE = "author-v1.0.0",
        WEKO_HANDLE_ALLOW_REGISTER_CNRI = True,
        WEKO_PERMISSION_ROLE_USER = ['System Administrator',
                             'Repository Administrator',
                             'Contributor',
                             'General',
                             'Community Administrator'],
        WEKO_RECORDS_UI_LICENSE_DICT=[
            {
                'name': _('write your own license'),
                'value': 'license_free',
            },
            # version 0
            {
                'name': _(
                    'Creative Commons CC0 1.0 Universal Public Domain Designation'),
                'code': 'CC0',
                'href_ja': 'https://creativecommons.org/publicdomain/zero/1.0/deed.ja',
                'href_default': 'https://creativecommons.org/publicdomain/zero/1.0/',
                'value': 'license_12',
                'src': '88x31(0).png',
                'src_pdf': 'cc-0.png',
                'href_pdf': 'https://creativecommons.org/publicdomain/zero/1.0/'
                            'deed.ja',
                'txt': 'This work is licensed under a Public Domain Dedication '
                    'International License.'
            },
            # version 3.0
            {
                'name': _('Creative Commons Attribution 3.0 Unported (CC BY 3.0)'),
                'code': 'CC BY 3.0',
                'href_ja': 'https://creativecommons.org/licenses/by/3.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by/3.0/',
                'value': 'license_6',
                'src': '88x31(1).png',
                'src_pdf': 'by.png',
                'href_pdf': 'http://creativecommons.org/licenses/by/3.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                       ' 3.0 International License.'
            },
            {
                'name': _(
                    'Creative Commons Attribution-ShareAlike 3.0 Unported '
                    '(CC BY-SA 3.0)'),
                'code': 'CC BY-SA 3.0',
                'href_ja': 'https://creativecommons.org/licenses/by-sa/3.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by-sa/3.0/',
                'value': 'license_7',
                'src': '88x31(2).png',
                'src_pdf': 'by-sa.png',
                'href_pdf': 'http://creativecommons.org/licenses/by-sa/3.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    '-ShareAlike 3.0 International License.'
            },
            {
                'name': _(
                    'Creative Commons Attribution-NoDerivs 3.0 Unported (CC BY-ND 3.0)'),
                'code': 'CC BY-ND 3.0',
                'href_ja': 'https://creativecommons.org/licenses/by-nd/3.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by-nd/3.0/',
                'value': 'license_8',
                'src': '88x31(3).png',
                'src_pdf': 'by-nd.png',
                'href_pdf': 'http://creativecommons.org/licenses/by-nd/3.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    '-NoDerivatives 3.0 International License.'

            },
            {
                'name': _(
                    'Creative Commons Attribution-NonCommercial 3.0 Unported'
                    ' (CC BY-NC 3.0)'),
                'code': 'CC BY-NC 3.0',
                'href_ja': 'https://creativecommons.org/licenses/by-nc/3.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by-nc/3.0/',
                'value': 'license_9',
                'src': '88x31(4).png',
                'src_pdf': 'by-nc.png',
                'href_pdf': 'http://creativecommons.org/licenses/by-nc/3.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    '-NonCommercial 3.0 International License.'
            },
            {
                'name': _(
                    'Creative Commons Attribution-NonCommercial-ShareAlike 3.0 '
                    'Unported (CC BY-NC-SA 3.0)'),
                'code': 'CC BY-NC-SA 3.0',
                'href_ja': 'https://creativecommons.org/licenses/by-nc-sa/3.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by-nc-sa/3.0/',
                'value': 'license_10',
                'src': '88x31(5).png',
                'src_pdf': 'by-nc-sa.png',
                'href_pdf': 'http://creativecommons.org/licenses/by-nc-sa/3.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    '-NonCommercial-ShareAlike 3.0 International License.'
            },
            {
                'name': _(
                    'Creative Commons Attribution-NonCommercial-NoDerivs '
                    '3.0 Unported (CC BY-NC-ND 3.0)'),
                'code': 'CC BY-NC-ND 3.0',
                'href_ja': 'https://creativecommons.org/licenses/by-nc-nd/3.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by-nc-nd/3.0/',
                'value': 'license_11',
                'src': '88x31(6).png',
                'src_pdf': 'by-nc-nd.png',
                'href_pdf': 'http://creativecommons.org/licenses/by-nc-nd/3.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    '-NonCommercial-ShareAlike 3.0 International License.'
            },
            # version 4.0
            {
                'name': _('Creative Commons Attribution 4.0 International (CC BY 4.0)'),
                'code': 'CC BY 4.0',
                'href_ja': 'https://creativecommons.org/licenses/by/4.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by/4.0/',
                'value': 'license_0',
                'src': '88x31(1).png',
                'src_pdf': 'by.png',
                'href_pdf': 'http://creativecommons.org/licenses/by/4.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    ' 4.0 International License.'
            },
            {
                'name': _(
                    'Creative Commons Attribution-ShareAlike 4.0 International '
                    '(CC BY-SA 4.0)'),
                'code': 'CC BY-SA 4.0',
                'href_ja': 'https://creativecommons.org/licenses/by-sa/4.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by-sa/4.0/',
                'value': 'license_1',
                'src': '88x31(2).png',
                'src_pdf': 'by-sa.png',
                'href_pdf': 'http://creativecommons.org/licenses/by-sa/4.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    '-ShareAlike 4.0 International License.'
            },
            {
                'name': _(
                    'Creative Commons Attribution-NoDerivatives 4.0 International '
                    '(CC BY-ND 4.0)'),
                'code': 'CC BY-ND 4.0',
                'href_ja': 'https://creativecommons.org/licenses/by-nd/4.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by-nd/4.0/',
                'value': 'license_2',
                'src': '88x31(3).png',
                'src_pdf': 'by-nd.png',
                'href_pdf': 'http://creativecommons.org/licenses/by-nd/4.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    '-NoDerivatives 4.0 International License.'
            },
            {
                'name': _(
                    'Creative Commons Attribution-NonCommercial 4.0 International'
                    ' (CC BY-NC 4.0)'),
                'code': 'CC BY-NC 4.0',
                'href_ja': 'https://creativecommons.org/licenses/by-nc/4.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by-nc/4.0/',
                'value': 'license_3',
                'src': '88x31(4).png',
                'src_pdf': 'by-nc.png',
                'href_pdf': 'http://creativecommons.org/licenses/by-nc/4.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    '-NonCommercial 4.0 International License.'
            },
            {
                'name': _(
                    'Creative Commons Attribution-NonCommercial-ShareAlike 4.0'
                    ' International (CC BY-NC-SA 4.0)'),
                'code': 'CC BY-NC-SA 4.0',
                'href_ja': 'https://creativecommons.org/licenses/by-nc-sa/4.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by-nc-sa/4.0/',
                'value': 'license_4',
                'src': '88x31(5).png',
                'src_pdf': 'by-nc-sa.png',
                'href_pdf': 'http://creativecommons.org/licenses/by-nc-sa/4.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    '-NonCommercial-ShareAlike 4.0 International License.'
            },
            {
                'name': _(
                    'Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 '
                    'International (CC BY-NC-ND 4.0)'),
                'code': 'CC BY-NC-ND 4.0',
                'href_ja': 'https://creativecommons.org/licenses/by-nc-nd/4.0/deed.ja',
                'href_default': 'https://creativecommons.org/licenses/by-nc-nd/4.0/',
                'value': 'license_5',
                'src': '88x31(6).png',
                'src_pdf': 'by-nc-nd.png',
                'href_pdf': 'http://creativecommons.org/licenses/by-nc-nd/4.0/',
                'txt': 'This work is licensed under a Creative Commons Attribution'
                    '-NonCommercial-ShareAlike 4.0 International License.'
            },
        ],
        WEKO_RECORDS_UI_BULK_UPDATE_FIELDS=WEKO_RECORDS_UI_BULK_UPDATE_FIELDS,
        WEKO_SEARCH_UI_BULK_EXPORT_URI = "URI_EXPORT_ALL",
        WEKO_SEARCH_UI_BULK_EXPORT_EXPIRED_TIME = 3,
        WEKO_SEARCH_UI_BULK_EXPORT_TASK = "KEY_EXPORT_ALL",
        WEKO_ADMIN_CACHE_PREFIX = 'admin_cache_{name}_{user_id}',
        WEKO_INDEXTREE_JOURNAL_FORM_JSON_FILE = "schemas/schemaform.json",
        WEKO_INDEXTREE_JOURNAL_REST_ENDPOINTS = dict(
            tid=dict(
                record_class='weko_indextree_journal.api:Journals',
                admin_indexjournal_route='/admin/indexjournal/<int:journal_id>',
                journal_route='/admin/indexjournal',
                # item_tree_journal_route='/tree/journal/<int:pid_value>',
                # journal_move_route='/tree/journal/move/<int:index_id>',
                default_media_type='application/json',
                create_permission_factory_imp='weko_indextree_journal.permissions:indextree_journal_permission',
                read_permission_factory_imp='weko_indextree_journal.permissions:indextree_journal_permission',
                update_permission_factory_imp='weko_indextree_journal.permissions:indextree_journal_permission',
                delete_permission_factory_imp='weko_indextree_journal.permissions:indextree_journal_permission',
            )
        ),
        WEKO_OPENSEARCH_SYSTEM_SHORTNAME = "WEKO",
        WEKO_BUCKET_QUOTA_SIZE = WEKO_BUCKET_QUOTA_SIZE,
        WEKO_MAX_FILE_SIZE = WEKO_MAX_FILE_SIZE,
        WEKO_OPENSEARCH_SYSTEM_DESCRIPTION = (
            "WEKO - NII Scholarly and Academic Information Navigator"
        ),
        WEKO_OPENSEARCH_IMAGE_URL = "static/favicon.ico",
        WEKO_ADMIN_OUTPUT_FORMAT = 'tsv',
        WEKO_THEME_DEFAULT_COMMUNITY = 'Root Index',
        WEKO_ITEMS_UI_OUTPUT_REGISTRATION_TITLE="",
        WEKO_ITEMS_UI_MULTIPLE_APPROVALS=True,
        WEKO_THEME_ADMIN_ITEM_MANAGEMENT_TEMPLATE = 'weko_theme/admin/item_management_display.html',
        THEME_BODY_TEMPLATE=THEME_BODY_TEMPLATE,
        WEKO_THEME_ADMIN_ITEM_MANAGEMENT_INIT_TEMPLATE=WEKO_THEME_ADMIN_ITEM_MANAGEMENT_INIT_TEMPLATE,
        WEKO_SEARCH_REST_ENDPOINTS = dict(
            recid=dict(
                pid_type='recid',
                pid_minter='recid',
                pid_fetcher='recid',
                pid_value='1.0',
                search_class=RecordsSearch,
                # search_index="test-weko",
                # search_index=SEARCH_UI_SEARCH_INDEX,
                search_index="test-weko",
                search_type='item-v1.0.0',
                search_factory_imp='weko_search_ui.query.weko_search_factory',
                # record_class='',
                record_serializers={
                    'application/json': ('invenio_records_rest.serializers'
                                        ':json_v1_response'),
                },
                search_serializers={
                    'application/json': ('weko_records.serializers'
                                        ':json_v1_search'),
                },
                index_route='/index/',
                tree_route='/index',
                item_tree_route='/index/<string:pid_value>',
                index_move_route='/index/move/<int:index_id>',
                links_factory_imp='weko_search_ui.links:default_links_factory',
                default_media_type='application/json',
                max_result_window=10000,
            ),
        ),
        WEKO_INDEX_TREE_REST_ENDPOINTS = dict(
            tid=dict(
                record_class='weko_index_tree.api:Indexes',
                index_route='/tree/index/<int:index_id>',
                tree_route='/tree',
                item_tree_route='/tree/<string:pid_value>',
                index_move_route='/tree/move/<int:index_id>',
                default_media_type='application/json',
                create_permission_factory_imp='weko_index_tree.permissions:index_tree_permission',
                read_permission_factory_imp='weko_index_tree.permissions:index_tree_permission',
                update_permission_factory_imp='weko_index_tree.permissions:index_tree_permission',
                delete_permission_factory_imp='weko_index_tree.permissions:index_tree_permission',
            )
        ),
        WEKO_INDEX_TREE_STYLE_OPTIONS = {
            'id': 'weko',
            'widths': ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11']
        },
        WEKO_SEARCH_TYPE_KEYWORD = "keyword",
        WEKO_SEARCH_UI_SEARCH_TEMPLATE = "weko_search_ui/search.html",
        WEKO_INDEX_TREE_INDEX_ADMIN_TEMPLATE = 'weko_index_tree/admin/index_edit_setting.html',
        WEKO_INDEX_TREE_LIST_API = "/api/tree",
        WEKO_INDEX_TREE_API = "/api/tree/index/",
        WEKO_SEARCH_UI_TO_NUMBER_FORMAT = "99999999999999.99",
        WEKO_SEARCH_UI_BASE_TEMPLATE=WEKO_SEARCH_UI_BASE_TEMPLATE,
    )
    app_.url_map.converters['pid'] = PIDConverter
    app_.config['RECORDS_REST_ENDPOINTS']['recid']['search_class'] = search_class

    # Parameterize application.
    if hasattr(request, 'param'):
        if 'endpoint' in request.param:
            app.config['RECORDS_REST_ENDPOINTS']['recid'].update(
                request.param['endpoint'])
        if 'records_rest_endpoints' in request.param:
            original_endpoint = app.config['RECORDS_REST_ENDPOINTS']['recid']
            del app.config['RECORDS_REST_ENDPOINTS']['recid']
            for new_endpoint_prefix, new_endpoint_value in \
                    request.param['records_rest_endpoints'].items():
                new_endpoint = dict(original_endpoint)
                new_endpoint.update(new_endpoint_value)
                app.config['RECORDS_REST_ENDPOINTS'][new_endpoint_prefix] = \
                    new_endpoint

    FlaskCeleryExt(app_)
    Menu(app_)
    Babel(app_)
    InvenioDB(app_)
    InvenioAccounts(app_)
    InvenioAccess(app_)
    InvenioAssets(app_)
    InvenioCache(app_)
    InvenioJSONSchemas(app_)
    InvenioSearch(app_)
    InvenioRecords(app_)
    InvenioREST(app_)
    InvenioIndexer(app_)
    InvenioI18N(app_)
    InvenioPIDRelations(app_)
    InvenioOAIServer(app_)
    InvenioMail(app_)
    InvenioStats(app_)
    InvenioAdmin(app_)
    InvenioPIDStore(app_)
    WekoRecords(app_)
    WekoSearchUI(app_)
    WekoWorkflow(app_)
    WekoGroups(app_)
    WekoAdmin(app_)
    # WekoTheme(app_)
    # InvenioCommunities(app_)
    
    # search = InvenioSearch(app_, client=MockEs())
    # search.register_mappings(search_class.Meta.index, 'mock_module.mappings')
    InvenioRecordsREST(app_)
    # app_.register_blueprint(create_blueprint_from_app(app_))
    # app_.register_blueprint(weko_theme_blueprint)
    # app_.register_blueprint(invenio_communities_blueprint)

    current_assets = LocalProxy(lambda: app_.extensions["invenio-assets"])
    current_assets.collect.collect()
    
    return app_


@pytest.yield_fixture()
def app(base_app):
    """Flask application fixture."""
    with base_app.app_context():
        yield base_app


@pytest.yield_fixture()
def db(app):
    """Get setup database."""
    if not database_exists(str(db_.engine.url)):
        create_database(str(db_.engine.url))
    db_.create_all()
    yield db_
    db_.session.remove()
    db_.drop_all()
    drop_alembic_version_table()


@pytest.yield_fixture()
def i18n_app(app):
    with app.test_request_context(
        headers=[('Accept-Language','ja')]):
        app.extensions['invenio-oauth2server'] = 1
        app.extensions['invenio-queues'] = 1
        yield app


@pytest.fixture
def indices(app, db):
    with db.session.begin_nested():
        # Create a test Indices
        testIndexOne = Index(index_name="testIndexOne",browsing_role="Contributor",public_state=True,id=11)
        testIndexTwo = Index(index_name="testIndexTwo",browsing_group="group_test1",public_state=True,id=22)
        testIndexThree = Index(
            index_name="testIndexThree",
            browsing_role="Contributor",
            public_state=True,
            harvest_public_state=True,
            id=33,
            item_custom_sort={'1': 1},
            public_date=datetime.today() - timedelta(days=1)
        )
        testIndexThreeChild = Index(
            index_name="testIndexThreeChild",
            browsing_role="Contributor",
            parent=33,
            index_link_enabled=True,
            index_link_name="test_link",
            public_state=True,
            harvest_public_state=False,
            id=44,
            public_date=datetime.today() - timedelta(days=1)
        )
        testIndexMore = Index(index_name="testIndexMore",parent=33,public_state=True,id='more')
        testIndexPrivate = Index(index_name="testIndexPrivate",public_state=False,id=55)

        db.session.add(testIndexThree)
        db.session.add(testIndexThreeChild)
        
    return {
        'index_dict': dict(testIndexThree),
        'index_non_dict': testIndexThree,
        'index_non_dict_child': testIndexThreeChild,
    }


@pytest.fixture
def record(app, db):
    i = 1
    record_data =  {
        "_oai": {
            "id": "oai:weko3.example.org:000000{:02d}".format(i),
            "sets": ["{}".format((i % 2) + 1)],
        },
        "path": ["{}".format((i % 2) + 1)],
        "recid": "{}".format(i),
        "pubdate": {"attribute_name": "PubDate", "attribute_value": "2022-08-20"},
        "_buckets": {"deposit": "3e99cfca-098b-42ed-b8a0-20ddd09b3e02"},
        "_deposit": {
            "id": "{}".format(i),
            "pid": {"type": "depid", "value": "{}".format(i), "revision_id": 0},
            "owner": "1",
            "owners": [1],
            "status": "draft",
            "created_by": 1,
            "owners_ext": {
                "email": "wekosoftware@nii.ac.jp",
                "username": "",
                "displayname": "",
            },
        },
        "item_title": "title",
        "author_link": [],
        "item_type_id": "1",
        "publish_date": "2022-08-20",
        "publish_status": "1",
        "weko_shared_id": -1,
        "item_1617186331708": {
            "attribute_name": "Title",
            "attribute_value_mlt": [
                {"subitem_1551255647225": "タイトル", "subitem_1551255648112": "ja"},
                {"subitem_1551255647225": "title", "subitem_1551255648112": "en"},
            ],
        },
        "item_1617258105262": {
            "attribute_name": "Resource Type",
            "attribute_value_mlt": [
                {
                    "resourceuri": "http://purl.org/coar/resource_type/c_5794",
                    "resourcetype": "conference paper",
                }
            ],
        },
        "relation_version_is_last": True,
        "item_1617605131499": {
            "attribute_name": "File",
            "attribute_type": "file",
            "attribute_value_mlt": [
                {
                    "url": {
                        "url": "https://weko3.example.org/record/{}/files/hello.txt".format(
                            i
                        )
                    },
                    "date": [{"dateType": "Available", "dateValue": "2022-09-07"}],
                    "format": "plain/text",
                    "filename": "hello.txt",
                    "filesize": [{"value": "146 KB"}],
                    "accessrole": "open_access",
                    "version_id": "",
                    "mimetype": "application/pdf",
                    "file": "",
                }
            ],
        },
    }

    rec_uuid = uuid.uuid4()
    record = WekoRecord.create(record_data, id_=rec_uuid)

    db.session.add(record)
    db.session.commit()

    return {"record": record, "rec_uuid": rec_uuid}


@pytest.fixture()
def users(app, db):
    """Create users."""
    ds = app.extensions['invenio-accounts'].datastore
    user_count = User.query.filter_by(email='user@test.org').count()
    if user_count != 1:
        user = create_test_user(email='user@test.org')
        contributor = create_test_user(email='contributor@test.org')
        comadmin = create_test_user(email='comadmin@test.org')
        repoadmin = create_test_user(email='repoadmin@test.org')
        sysadmin = create_test_user(email='sysadmin@test.org')
        generaluser = create_test_user(email='generaluser@test.org')
        originalroleuser = create_test_user(email='originalroleuser@test.org')
        originalroleuser2 = create_test_user(email='originalroleuser2@test.org')
        noroleuser = create_test_user(email='noroleuser@test.org')
    else:
        user = User.query.filter_by(email='user@test.org').first()
        contributor = User.query.filter_by(email='contributor@test.org').first()
        comadmin = User.query.filter_by(email='comadmin@test.org').first()
        repoadmin = User.query.filter_by(email='repoadmin@test.org').first()
        sysadmin = User.query.filter_by(email='sysadmin@test.org').first()
        generaluser = User.query.filter_by(email='generaluser@test.org')
        originalroleuser = create_test_user(email='originalroleuser@test.org')
        originalroleuser2 = create_test_user(email='originalroleuser2@test.org')
        noroleuser = create_test_user(email='noroleuser@test.org')
        
    role_count = Role.query.filter_by(name='System Administrator').count()
    if role_count != 1:
        sysadmin_role = ds.create_role(name='System Administrator')
        repoadmin_role = ds.create_role(name='Repository Administrator')
        contributor_role = ds.create_role(name='Contributor')
        comadmin_role = ds.create_role(name='Community Administrator')
        general_role = ds.create_role(name='General')
        originalrole = ds.create_role(name='Original Role')
    else:
        sysadmin_role = Role.query.filter_by(name='System Administrator').first()
        repoadmin_role = Role.query.filter_by(name='Repository Administrator').first()
        contributor_role = Role.query.filter_by(name='Contributor').first()
        comadmin_role = Role.query.filter_by(name='Community Administrator').first()
        general_role = Role.query.filter_by(name='General').first()
        originalrole = Role.query.filter_by(name='Original Role').first()

    ds.add_role_to_user(sysadmin, sysadmin_role)
    ds.add_role_to_user(repoadmin, repoadmin_role)
    ds.add_role_to_user(contributor, contributor_role)
    ds.add_role_to_user(comadmin, comadmin_role)
    ds.add_role_to_user(generaluser, general_role)
    ds.add_role_to_user(originalroleuser, originalrole)
    ds.add_role_to_user(originalroleuser2, originalrole)
    ds.add_role_to_user(user, sysadmin_role)
    ds.add_role_to_user(user, repoadmin_role)
    ds.add_role_to_user(user, contributor_role)
    ds.add_role_to_user(user, comadmin_role)
    
    # Assign access authorization
    with db.session.begin_nested():
        action_users = [
            ActionUsers(action='superuser-access', user=sysadmin)
        ]
        db.session.add_all(action_users)
        action_roles = [
            ActionRoles(action='superuser-access', role=sysadmin_role),
            ActionRoles(action='admin-access', role=repoadmin_role),
            ActionRoles(action='schema-access', role=repoadmin_role),
            ActionRoles(action='index-tree-access', role=repoadmin_role),
            ActionRoles(action='indextree-journal-access', role=repoadmin_role),
            ActionRoles(action='item-type-access', role=repoadmin_role),
            ActionRoles(action='item-access', role=repoadmin_role),
            ActionRoles(action='files-rest-bucket-update', role=repoadmin_role),
            ActionRoles(action='files-rest-object-delete', role=repoadmin_role),
            ActionRoles(action='files-rest-object-delete-version', role=repoadmin_role),
            ActionRoles(action='files-rest-object-read', role=repoadmin_role),
            ActionRoles(action='search-access', role=repoadmin_role),
            ActionRoles(action='detail-page-acces', role=repoadmin_role),
            ActionRoles(action='download-original-pdf-access', role=repoadmin_role),
            ActionRoles(action='author-access', role=repoadmin_role),
            ActionRoles(action='items-autofill', role=repoadmin_role),
            ActionRoles(action='stats-api-access', role=repoadmin_role),
            ActionRoles(action='read-style-action', role=repoadmin_role),
            ActionRoles(action='update-style-action', role=repoadmin_role),
            ActionRoles(action='detail-page-acces', role=repoadmin_role),

            ActionRoles(action='admin-access', role=comadmin_role),
            ActionRoles(action='index-tree-access', role=comadmin_role),
            ActionRoles(action='indextree-journal-access', role=comadmin_role),
            ActionRoles(action='item-access', role=comadmin_role),
            ActionRoles(action='files-rest-bucket-update', role=comadmin_role),
            ActionRoles(action='files-rest-object-delete', role=comadmin_role),
            ActionRoles(action='files-rest-object-delete-version', role=comadmin_role),
            ActionRoles(action='files-rest-object-read', role=comadmin_role),
            ActionRoles(action='search-access', role=comadmin_role),
            ActionRoles(action='detail-page-acces', role=comadmin_role),
            ActionRoles(action='download-original-pdf-access', role=comadmin_role),
            ActionRoles(action='author-access', role=comadmin_role),
            ActionRoles(action='items-autofill', role=comadmin_role),
            ActionRoles(action='detail-page-acces', role=comadmin_role),
            ActionRoles(action='detail-page-acces', role=comadmin_role),

            ActionRoles(action='item-access', role=contributor_role),
            ActionRoles(action='files-rest-bucket-update', role=contributor_role),
            ActionRoles(action='files-rest-object-delete', role=contributor_role),
            ActionRoles(action='files-rest-object-delete-version', role=contributor_role),
            ActionRoles(action='files-rest-object-read', role=contributor_role),
            ActionRoles(action='search-access', role=contributor_role),
            ActionRoles(action='detail-page-acces', role=contributor_role),
            ActionRoles(action='download-original-pdf-access', role=contributor_role),
            ActionRoles(action='author-access', role=contributor_role),
            ActionRoles(action='items-autofill', role=contributor_role),
            ActionRoles(action='detail-page-acces', role=contributor_role),
            ActionRoles(action='detail-page-acces', role=contributor_role),
        ]
        db.session.add_all(action_roles)

    return [
        {'email': noroleuser.email, 'id': noroleuser.id, 'obj': noroleuser},
        {'email': contributor.email, 'id': contributor.id, 'obj': contributor},
        {'email': repoadmin.email, 'id': repoadmin.id, 'obj': repoadmin},
        {'email': sysadmin.email, 'id': sysadmin.id, 'obj': sysadmin},
        {'email': comadmin.email, 'id': comadmin.id, 'obj': comadmin},
        {'email': generaluser.email, 'id': generaluser.id, 'obj': sysadmin},
        {'email': originalroleuser.email, 'id': originalroleuser.id, 'obj': originalroleuser},
        {'email': originalroleuser2.email, 'id': originalroleuser2.id, 'obj': originalroleuser2},
        {'email': user.email, 'id': user.id, 'obj': user},
    ]


