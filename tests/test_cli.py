"""
http://click.pocoo.org/5/testing/
"""

import os
import json
import logging
import random
import time
import unittest

import pytest
from click.testing import CliRunner
import anonlinkclient
import anonlinkclient.cli as cli
from clkhash import randomnames, schema

from anonlinkclient.rest_client import ServiceError, RestClient

from tests import *

ES_TIMEOUT = os.environ.get("ES_TIMEOUT", 60)


class CLITestHelper(unittest.TestCase):
    SAMPLES = 100

    @classmethod
    def setUpClass(cls) -> None:
        CLITestHelper.pii_file = create_temp_file()
        CLITestHelper.pii_file_2 = create_temp_file()

        # Get random PII
        pii_data = randomnames.NameList(CLITestHelper.SAMPLES)
        data = [(name, dob) for _, name, dob, _ in pii_data.names]

        headers = ['NAME freetext', 'DOB YYYY/MM/DD']
        randomnames.save_csv(data, headers, CLITestHelper.pii_file)

        random.shuffle(data)
        randomnames.save_csv(data[::2], headers, CLITestHelper.pii_file_2)

        CLITestHelper.default_schema = [
            {"identifier": "INDEX"},
            {"identifier": "NAME freetext"},
            {"identifier": "DOB YYYY/MM/DD"},
            {"identifier": "GENDER M or F"}
        ]

        CLITestHelper.pii_file.close()
        CLITestHelper.pii_file_2.close()

    def setUp(self):
        super(CLITestHelper, self).setUp()

    @classmethod
    def tearDownClass(cls) -> None:
        # Delete temporary files if they exist.
        for f in CLITestHelper.pii_file, CLITestHelper.pii_file_2:
            try:
                os.remove(f.name)
            except:
                pass

    def tearDown(self):
        super(CLITestHelper, self).tearDown()

    def run_command_capture_output(self, command):
        """
        Creates a NamedTempFile and saves the output of running a
        cli command to that file by adding `-o output.name` to the
        command before running it.

        :param command: e.g ["status"]
        :returns: The output as a string.
        :raises: AssertionError if the command's exit code isn't 0
        """

        runner = CliRunner()

        with temporary_file() as output_filename:
            command.extend(['-o', output_filename])
            cli_result = runner.invoke(cli.cli, command)
            assert cli_result.exit_code == 0,\
                "Output:\n{}\nException:\n{}".format(cli_result.output, cli_result.exception)
            with open(output_filename, 'rt') as output:
                return output.read()

    def run_command_load_json_output(self, command):
        """
         Parses the file as JSON.

        :param command: e.g ["status"]
        :return: The parsed JSON in the created output file.
        :raises: AssertionError if the command's exit code isn't 0
        :raises: json.decoder.JSONDecodeError if the output isn't json
        """
        logging.info(command)
        output_str = self.run_command_capture_output(command)
        return json.loads(output_str)


class BasicCLITests(unittest.TestCase):

    def test_list_commands(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, [])
        expected_options = ['--version', '--verbose', '--help']
        expected_commands = ['benchmark', 'create', 'create-project', 'delete', 'delete-project', 'describe',
                             'generate', 'generate-default-schema', 'hash', 'results', 'status', 'upload',
                             'validate-schema']
        for expected_option in expected_options:
            assert expected_option in result.output

        for expected_command in expected_commands:
            assert expected_command in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ['--version'])
        assert result.exit_code == 0
        assert anonlinkclient.__version__ in result.output

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, '--help')
        result_without_command = runner.invoke(cli.cli, [])
        assert result.output == result_without_command.output

    def test_bench(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ['benchmark'])
        assert 'hashes in' in result.output

    def test_describe(self):
        runner = CliRunner()

        with runner.isolated_filesystem():
            with open('in.csv', 'w') as f:
                f.write('Alice,1967/09/27')

            runner.invoke(
                cli.cli,
                ['hash', 'in.csv', 'a', SIMPLE_SCHEMA_PATH,
                 'out.json', '--no-header'])

            result = runner.invoke(cli.cli,
                                   ['describe', 'out.json'])
            assert result.exit_code == 0


class TestSchemaValidationCommand(unittest.TestCase):

    @staticmethod
    def validate_schema(schema_path):
        runner = CliRunner()
        result = runner.invoke(cli.cli, [
            'validate-schema', schema_path
        ])
        return result

    def test_good_v1_schema(self):
        for schema_path in GOOD_SCHEMA_V1_PATH, SIMPLE_SCHEMA_PATH:
            result = self.validate_schema(schema_path)
            assert result.exit_code == 0
            assert 'schema is valid' in result.output

    def test_bad_v1_schema(self):
        result = self.validate_schema(BAD_SCHEMA_V1_PATH)
        assert result.exit_code == -1
        assert 'schema is not valid.' in result.output
        assert "'l' is a required property" in result.output

    def test_good_v2_schema(self):
        for schema_path in GOOD_SCHEMA_V2_PATH, RANDOMNAMES_SCHEMA_PATH:
            result = self.validate_schema(schema_path)
            assert result.exit_code == 0
            assert 'schema is valid' in result.output

    def test_bad_v2_schema(self):
        result = self.validate_schema(BAD_SCHEMA_V2_PATH)
        assert result.exit_code == -1
        assert 'schema is not valid.' in result.output

    def test_good_v3_schema(self):
        result = self.validate_schema(GOOD_SCHEMA_V3_PATH)
        assert result.exit_code == 0
        assert 'schema is valid' in result.output

    def test_bad_v3_schema(self):
        result = self.validate_schema(BAD_SCHEMA_V3_PATH)
        assert result.exit_code == -1
        assert 'schema is not valid.' in result.output


class TestSchemaConversionCommand(unittest.TestCase):

    LATEST_VERSION = max(schema.MASTER_SCHEMA_FILE_NAMES.keys())

    @staticmethod
    def convert_schema(schema_path):
        runner = CliRunner()
        result = runner.invoke(cli.cli, [
            'convert-schema', schema_path, 'out.json'
        ])
        return result

    def test_good_v1_schema(self):
        for schema_path in GOOD_SCHEMA_V1_PATH, SIMPLE_SCHEMA_PATH:
            result = self.convert_schema(schema_path)
            assert result.exit_code == 0
            with open('out.json') as f:
                json_dict = json.load(f)
                self.assertEqual(json_dict['version'], self.LATEST_VERSION)

    def test_bad_v1_schema(self):
        result = self.convert_schema(BAD_SCHEMA_V1_PATH)
        assert result.exit_code == 1
        self.assertIsInstance(result.exception, schema.SchemaError)
        assert 'schema is not valid.' in result.exception.msg
        assert "'l' is a required property" in result.exception.msg

    def test_good_v2_schema(self):
        for schema_path in GOOD_SCHEMA_V2_PATH, RANDOMNAMES_SCHEMA_PATH:
            result = self.convert_schema(schema_path)
            assert result.exit_code == 0
            with open('out.json') as f:
                json_dict = json.load(f)
                self.assertEqual(json_dict['version'], self.LATEST_VERSION)

    def test_bad_v2_schema(self):
        result = self.convert_schema(BAD_SCHEMA_V2_PATH)
        assert result.exit_code == 1
        self.assertIsInstance(result.exception, schema.SchemaError)
        assert 'schema is not valid.' in result.exception.msg

    def test_good_v3_schema(self):
        result = self.convert_schema(GOOD_SCHEMA_V3_PATH)
        assert result.exit_code == 0
        with open('out.json') as f:
            json_dict = json.load(f)
            self.assertEqual(json_dict['version'], self.LATEST_VERSION)

    def test_bad_v3_schema(self):
        result = self.convert_schema(BAD_SCHEMA_V3_PATH)
        assert result.exit_code == 1
        self.assertIsInstance(result.exception, schema.SchemaError)
        assert 'schema is not valid.' in result.exception.msg


class TestHashCommand(unittest.TestCase):

    def setUp(self):
        self.runner = CliRunner()

    def test_hash_auto_help(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ['hash'])
        assert 'Missing argument' in result.output

    def test_hash_help(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ['hash', '--help'])
        assert 'secret' in result.output.lower()
        assert 'schema' in result.output

    def test_hash_requires_secret(self):
        runner = self.runner

        with runner.isolated_filesystem():
            with open('in.csv', 'w') as f:
                f.write('Alice, 1967')

            result = runner.invoke(cli.cli,
                                   ['hash', 'in.csv'])
            assert result.exit_code != 0
            self.assertIn('Usage: anonlink hash', result.output)
            self.assertIn('Missing argument', result.output)

    def test_hash_with_provided_schema(self):
        runner = self.runner

        with runner.isolated_filesystem():
            with open('in.csv', 'w') as f:
                f.write('Alice,1967/09/27')

            result = runner.invoke(
                cli.cli,
                ['hash', 'in.csv', 'a', SIMPLE_SCHEMA_PATH,
                 'out.json', '--no-header'])

            with open('out.json') as f:
                self.assertIn('clks', json.load(f))

    def test_hash_febrl_data(self):
        runner = self.runner
        schema_file = os.path.join(
            os.path.dirname(__file__),
            'testdata/dirty-data-schema.json'
        )
        a_pii = os.path.join(
            os.path.dirname(__file__),
            'testdata/dirty_1000_50_1.csv'
        )

        with runner.isolated_filesystem():
            result = runner.invoke(
                cli.cli,
                ['hash', a_pii, 'a', schema_file, 'out.json'])

            result_2 = runner.invoke(
                cli.cli,
                ['hash', a_pii, 'a', schema_file, 'out-2.json'])

            with open('out.json') as f:
                hasha = json.load(f)['clks']

            with open('out-2.json') as f:
                hashb = json.load(f)['clks']

        for i in range(1000):
            self.assertEqual(hasha[i], hashb[i])

    def test_hash_wrong_schema(self):
        runner = self.runner

        # This schema only has 4 features
        schema_file = os.path.join(
            os.path.dirname(__file__),
            'testdata/randomnames-schema.json'
        )

        # This CSV has 14 features
        a_pii = os.path.join(
            os.path.dirname(__file__),
            'testdata/dirty_1000_50_1.csv'
        )

        with runner.isolated_filesystem():

            result = runner.invoke(cli.cli, ['hash',
                                                     '--quiet',
                                                     '--schema',
                                                            schema_file,
                                                            a_pii,
                                                     'a', 'b', '-'])

        assert result.exit_code != 0

    def test_hash_schemaerror(self):
        runner = self.runner

        schema_file = os.path.join(TESTDATA, 'bad-schema-v1.json')
        a_pii = os.path.join(TESTDATA, 'dirty_1000_50_1.csv')

        # with self.assertRaises(SchemaError):
        with runner.isolated_filesystem():
            result = runner.invoke(cli.cli,
                                   ['hash', a_pii, 'horse', schema_file, 'out.json'
                                    ])
        assert result.exit_code != 0
        assert 'schema is not valid' in result.output

    def test_hash_invalid_data(self):
        runner = self.runner
        with runner.isolated_filesystem():
            with open('in.csv', 'w') as f:
                f.write('Alice,')

            result = runner.invoke(
                cli.cli,
                ['hash', 'in.csv', 'a', SIMPLE_SCHEMA_PATH,
                 'out.json', '--no-header'])

            assert 'Invalid entry' in result.output


class TestBlockCommand(unittest.TestCase):

    def test_cli_includes_help(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ['--help'])
        self.assertEqual(result.exit_code, 0, result.output)

        assert 'block' in result.output.lower()

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ['--version'])
        assert result.exit_code == 0
        self.assertIn(anonlinkclient.__version__, result.output)

    def test_lambda_fold(self):
        runner = CliRunner()
        with temporary_file() as output_filename:
            with open(output_filename, 'wt') as output:
                schema_path = os.path.join(TESTDATA, 'lambda_fold_schema.json')
                data_path = os.path.join(TESTDATA, 'small.csv')
                cli_result = runner.invoke(
                    cli.cli,
                    ['block', data_path, schema_path, output.name])
            self.assertEqual(cli_result.exit_code, 0, msg='result={}; exception={}'.format(cli_result, cli_result.exception))

            with open(output_filename, 'rt') as output:
                outjson = json.load(output)
                self.assertIn('blocks', outjson)
                self.assertIn('state', outjson['meta'])
                self.assertIn('config', outjson['meta'])


class TestCompareCommand(unittest.TestCase):

    def setUp(self):
        self.runner = CliRunner()

    def test_cli_includes_help(self):
        result = self.runner.invoke(cli.cli, ['--help'])
        self.assertEqual(result.exit_code, 0, result.output)

        assert 'compare' in result.output.lower()

    def test_compare_ndiff(self):
        cli_result = self.runner.invoke(cli.cli, ['compare', '-n', os.path.join(TESTDATA, 'bad-schema-v2.json'), os.path.join(TESTDATA, 'bad-schema-v3.json')])
        self.assertEqual(cli_result.exit_code, 0, msg='result={}; exception={}'.format(cli_result, cli_result.exception))
        default_result = self.runner.invoke(cli.cli, ['compare', os.path.join(TESTDATA, 'bad-schema-v2.json'), os.path.join(TESTDATA, 'bad-schema-v3.json')])
        self.assertEqual(default_result.exit_code, 0, msg='result={}; exception={}'.format(default_result, default_result.exception))
        self.assertEqual(cli_result.output, default_result.output, msg='ndiff format is not the default, but should')
        self.assertIn('?', cli_result.output)

    def test_compare_context_diff(self):
        cli_result = self.runner.invoke(cli.cli, ['compare', '-c', os.path.join(TESTDATA, 'bad-schema-v2.json'),
                                                  os.path.join(TESTDATA, 'bad-schema-v3.json')])
        self.assertEqual(cli_result.exit_code, 0,
                         msg='result={}; exception={}'.format(cli_result, cli_result.exception))
        cli_result_larger_l = self.runner.invoke(cli.cli, ['compare', '-c', '-l 5',
                                                 os.path.join(TESTDATA, 'bad-schema-v2.json'),
                                                 os.path.join(TESTDATA, 'bad-schema-v3.json')])
        self.assertEqual(cli_result_larger_l.exit_code, 0,
                         msg='result={}; exception={}'.format(cli_result_larger_l, cli_result_larger_l.exception))
        self.assertGreater(cli_result_larger_l.output, cli_result.output)
        self.assertIn('!', cli_result.output)

    def test_compare_unified_diff(self):
        cli_result = self.runner.invoke(cli.cli, ['compare', '-u', os.path.join(TESTDATA, 'bad-schema-v2.json'),
                                                  os.path.join(TESTDATA, 'bad-schema-v3.json')])
        self.assertEqual(cli_result.exit_code, 0,
                         msg='result={}; exception={}'.format(cli_result, cli_result.exception))
        cli_result_larger_l = self.runner.invoke(cli.cli, ['compare', '-u', '-l 5',
                                                           os.path.join(TESTDATA, 'bad-schema-v2.json'),
                                                           os.path.join(TESTDATA, 'bad-schema-v3.json')])
        self.assertEqual(cli_result_larger_l.exit_code, 0,
                         msg='result={}; exception={}'.format(cli_result_larger_l, cli_result_larger_l.exception))
        self.assertGreater(cli_result_larger_l.output, cli_result.output)
        self.assertIn('@@', cli_result.output)

    def test_compare_html_diff(self):
        cli_result = self.runner.invoke(cli.cli, ['compare', '-m', os.path.join(TESTDATA, 'bad-schema-v2.json'),
                                                  os.path.join(TESTDATA, 'bad-schema-v3.json')])
        self.assertEqual(cli_result.exit_code, 0,
                         msg='result={}; exception={}'.format(cli_result, cli_result.exception))
        self.assertIn('<html>', cli_result.output)
        self.assertIn('</table>', cli_result.output)


class TestHasherDefaultSchema(unittest.TestCase):

    samples = 100

    def setUp(self):
        self.pii_file = create_temp_file()

        pii_data = randomnames.NameList(TestHasherDefaultSchema.samples)
        randomnames.save_csv(
            pii_data.names,
            [f.identifier for f in pii_data.SCHEMA.fields],
            self.pii_file)
        self.pii_file.flush()

    def test_cli_includes_help(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ['--help'])
        self.assertEqual(result.exit_code, 0, result.output)

        assert 'Usage' in result.output
        assert 'Options' in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli.cli, ['--version'])
        assert result.exit_code == 0
        self.assertIn(anonlinkclient.__version__, result.output)

    def test_generate_command(self):
        runner = CliRunner()
        with temporary_file() as output_filename:
            with open(output_filename) as output:
                cli_result = runner.invoke(
                    cli.cli,
                    ['generate', '50', output.name])
            self.assertEqual(cli_result.exit_code, 0, msg=cli_result.output)
            with open(output_filename, 'rt') as output:
                out = output.read()
        assert len(out) > 50

    def test_generate_default_schema_command(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            generate_schema_result = runner.invoke(
                cli.cli,
                ['generate-default-schema', 'pii-schema.json'])
            self.assertEqual(generate_schema_result.exit_code, 0,
                             msg=generate_schema_result.output)

            hash_result = runner.invoke(
                cli.cli,
                ['hash', self.pii_file.name, 'secret',
                 'pii-schema.json', 'pii-hashes.json'])
            self.assertEqual(hash_result.exit_code, 0, msg=hash_result.output)

    def test_basic_hashing(self):
        runner = CliRunner()
        with temporary_file() as output_filename:
            with open(output_filename, 'wt') as output:
                cli_result = runner.invoke(
                    cli.cli,
                    ['hash', self.pii_file.name, 'secret',
                     RANDOMNAMES_SCHEMA_PATH, output.name])
            self.assertEqual(cli_result.exit_code, 0, msg=cli_result.output)

            with open(output_filename, 'rt') as output:
                self.assertIn('clks', json.load(output))


class TestHasherSchema(CLITestHelper):
    def test_hashing_json_schema(self):
        runner = CliRunner()

        pii_data = randomnames.NameList(self.SAMPLES)
        pii_file = create_temp_file()
        randomnames.save_csv(pii_data.names,
                             [f.identifier for f in pii_data.SCHEMA.fields],
                             pii_file)
        pii_file.close()

        with temporary_file() as output_filename:
            with open(output_filename) as output:
                cli_result = runner.invoke(
                    cli.cli,
                    ['hash', pii_file.name, 'secret', RANDOMNAMES_SCHEMA_PATH, output.name])

            self.assertEqual(cli_result.exit_code, 0, msg=cli_result.output)

            with open(output_filename) as output:
                self.assertIn('clks', json.load(output))


@unittest.skipUnless("TEST_ENTITY_SERVICE" in os.environ,
                     "Set envvar TEST_ENTITY_SERVICE to https://testing.es.data61.xyz or a valid URL of an "
                     "entity service deployment")
class TestCliInteractionWithService(CLITestHelper):

    server_options = ['--server', '--retry-multiplier', '--retry-exponential-max', '--retry-max-time']

    retry_options_values = ['--retry-multiplier', 50, '--retry-exponential-max', 1000, '--retry-max-time', 30000]

    @classmethod
    def setUpClass(cls) -> None:
        super(TestCliInteractionWithService, cls).setUpClass()
        TestCliInteractionWithService.clk_file = create_temp_file()
        TestCliInteractionWithService.clk_file_2 = create_temp_file()

        TestCliInteractionWithService.block_file = create_temp_file()
        TestCliInteractionWithService.block_file_2 = create_temp_file()

        # hash some PII for uploading
        # TODO don't need to rehash data for every test
        runner = CliRunner()
        cli_result = runner.invoke(cli.cli,
                                   ['hash',
                                    TestCliInteractionWithService.pii_file.name,
                                    'secret',
                                    SIMPLE_SCHEMA_PATH,
                                    TestCliInteractionWithService.clk_file.name])
        assert cli_result.exit_code == 0

        cli_result = runner.invoke(cli.cli,
                                   ['hash',
                                    TestCliInteractionWithService.pii_file_2.name,
                                    'secret',
                                    SIMPLE_SCHEMA_PATH,
                                    TestCliInteractionWithService.clk_file_2.name])
        assert cli_result.exit_code == 0

        # generate blocks for both PII
        block_result = runner.invoke(cli.cli,
                                     ['block',
                                      TestCliInteractionWithService.pii_file.name,
                                      SAMPLE_BLOCK_SCHEMA_PATH,
                                      TestCliInteractionWithService.block_file.name])
        print(block_result.exception)
        print(block_result.exc_info)
        print(block_result.output)

        assert block_result.exit_code == 0

        block_result = runner.invoke(cli.cli,
                                     ['block',
                                      TestCliInteractionWithService.pii_file_2.name,
                                      SAMPLE_BLOCK_SCHEMA_PATH,
                                      TestCliInteractionWithService.block_file_2.name])
        assert block_result.exit_code == 0

        TestCliInteractionWithService.clk_file.close()
        TestCliInteractionWithService.clk_file_2.close()

    def setUp(self):
        super(TestCliInteractionWithService, self).setUp()
        self.url = os.environ['TEST_ENTITY_SERVICE']

        self.rest_client = RestClient(self.url)

        self._created_projects = []

    @classmethod
    def tearDownClass(cls) -> None:
        super(TestCliInteractionWithService, cls).tearDownClass()
        try:
            os.remove(TestCliInteractionWithService.clk_file.name)
            os.remove(TestCliInteractionWithService.clk_file_2.name)
        except:
            pass

    def tearDown(self):
        super(TestCliInteractionWithService, self).tearDown()
        self.delete_created_projects()

    def delete_created_projects(self):
        for project in self._created_projects:
            try:
                self.rest_client.project_delete(project['project_id'], project['result_token'])
            except KeyError:
                pass
            except ServiceError:
                # probably already deleted
                pass

    def _create_project(self, project_args=None):
        command = ['create-project', '--server', self.url, '--schema', SIMPLE_SCHEMA_PATH]
        if project_args is not None:
            for key in project_args:
                command.append('--{}'.format(key))
                # only append value if this argument is not a flag
                if project_args[key] != 'True':
                    command.append(project_args[key])

        project = self.run_command_load_json_output(command)
        self._created_projects.append(project)
        return project

    def _create_project_and_run(self, project_args=None, run_args=None):
        project = self._create_project(project_args)

        threshold = run_args['threshold'] if run_args is not None and 'threshold' in run_args else 0.99

        command = [
            'create',
            '--server', self.url,
            '--threshold', str(threshold),
            '--project', project['project_id'],
            '--apikey', project['result_token'],
        ]

        if run_args is not None:
            for key in run_args:
                command.append('--{}'.format(key))
                command.append(run_args[key])

        run = self.run_command_load_json_output(command)
        return project, run

    def _test_helps(self, command, list_expected_commands, include_server_options=False):
        runner = CliRunner()
        result = runner.invoke(cli.cli, [command, '--help'])

        if include_server_options:
            list_to_test = self.server_options + list_expected_commands
        else:
            list_to_test = list_expected_commands
        for option in list_to_test:
            self.assertIn(option, result.output)

    def test_status_help(self):
        self._test_helps('status', ['--output', '--verbose', '--help'], include_server_options=True)

    def test_status(self):
        self.run_command_load_json_output(['status', '--server', self.url])

    def test_status_retry_options(self):
        self.run_command_load_json_output(['status', '--server', self.url] + self.retry_options_values)

    def test_status_invalid_server_raises(self):
        with pytest.raises(AssertionError) as exec_info:
            self.run_command_capture_output(['status', '--server', 'https://example.com'])

            self.assertIn('invalid choice', exec_info.value.args[0])

    def _test_create_project(self, out):
        self.assertIn('project_id', out)
        self.assertIn('result_token', out)
        self.assertIn('update_tokens', out)

        self.assertGreaterEqual(len(out['project_id']), 16)
        self.assertGreaterEqual(len(out['result_token']), 16)
        self.assertGreaterEqual(len(out['update_tokens']), 2)

    def test_create_project(self):
        out = self._create_project()
        self._test_create_project(out)

    def test_create_project_retry_options(self):
        out = self._create_project({'retry-multiplier': 50, 'retry-exponential-max': 1000, 'retry-max-time': 30000})
        self._test_create_project(out)

    def test_create_project_help(self):
        self._test_helps('create-project',
                         ['--type', '--schema', '--name', '--parties', '--output', '--verbose', '--help'],
                         include_server_options=True)

    def test_create_project_2_party(self):
        out = self._create_project(project_args={'parties': '2'})
        self._test_create_project(out)

    def test_create_project_multi_party(self):
        out = self._create_project(
            project_args={'parties': '3', 'type': 'groups'})

        self.assertIn('project_id', out)
        self.assertIn('result_token', out)
        self.assertIn('update_tokens', out)

        self.assertGreaterEqual(len(out['project_id']), 16)
        self.assertGreaterEqual(len(out['result_token']), 16)
        self.assertGreaterEqual(len(out['update_tokens']), 3)

    def test_create_project_invalid_parties_type(self):
        with pytest.raises(AssertionError) as exec_info:
            self._create_project(project_args={'parties': '3'})

        assert "requires result type 'groups'"  in exec_info.value.args[0]

    def test_create_project_bad_type(self):
        with pytest.raises(AssertionError) as exec_info:
            self._create_project(project_args={'type': 'invalid'})

        assert 'invalid choice' in exec_info.value.args[0]

    def test_create_project_and_run(self):
        project, run = self._create_project_and_run()

        self.assertIn('project_id', project)
        self.assertIn('run_id', run)

    def _test_delete_run(self, extra_arguments):
        project, run = self._create_project_and_run()

        command = [
                'delete',
                '--server', self.url,
                '--project', project['project_id'],
                '--run', run['run_id'],
                '--apikey', project['result_token']
            ] + extra_arguments
        runner = CliRunner()

        cli_result = runner.invoke(cli.cli, command)
        assert cli_result.exit_code == 0, cli_result.output

        # TODO get runs and check it is gone?

        with pytest.raises(ServiceError):
            self.rest_client.run_get_status(project['project_id'],
                                            project['result_token'],
                                            run['run_id']
                                            )

    def test_delete_run(self):
        self._test_delete_run([])

    def test_delete_run_retry_options(self):
        self._test_delete_run(self.retry_options_values)

    def test_delete_run_help(self):
        self._test_helps('delete', ['--project', '--run', '--apikey', '--verbose', '--help'],
                         include_server_options=True)

    def _test_delete_project(self, extra_arguments):
        project, run = self._create_project_and_run()

        runner = CliRunner()
        command = [
            'delete-project',
            '--server', self.url,
            '--project', project['project_id'],
            '--apikey', project['result_token']
        ] + extra_arguments
        cli_result = runner.invoke(cli.cli, command)
        assert cli_result.exit_code == 0, cli_result.output

        with pytest.raises(ServiceError):
            self.rest_client.project_get_description(project['project_id'], project['result_token'])

    def test_delete_project(self):
        self._test_delete_project([])

    def test_delete_project_retry_options(self):
        self._test_delete_project(self.retry_options_values)

    def test_delete_project_help(self):
        self._test_helps('delete-project', ['--project', '--apikey', '--verbose', '--help'],
                         include_server_options=True)

    def test_create_help(self):
        self._test_helps('create', ['--name', '--project', '--apikey', '--output', '--threshold', '--verbose', '--help'],
                         include_server_options=True)

    def test_create_with_optional_name(self):
        out = self._create_project({'name': 'testprojectname'})
        self._test_create_project(out)

    def test_create_with_bad_schema(self):
        # Make sure we don't succeed with bad schema.
        schema_path = os.path.join(os.path.dirname(__file__), 'testdata', 'bad-schema-v1.json')
        with pytest.raises(AssertionError):
            self.run_command_load_json_output(
                [
                    'create-project',
                    '--server', self.url,
                    '--schema', schema_path
                ]
            )

    def test_get_temp_credential(self):
        project = self._create_project()
        res = self.rest_client.get_temporary_objectstore_credentials(
                    project['project_id'],
                    project['update_tokens'][0])
        assert 'credentials' in res
        assert 'AccessKeyId' in res['credentials']

    def test_upload_help(self):
        self._test_helps('upload', ['--project', '--apikey', '--output', '--verbose', '--help'],
                         include_server_options=True)

    def _test_single_upload(self, extra_arguments):
        project = self._create_project()

        # Upload
        self.run_command_load_json_output(
            [
                'upload',
                '--server', self.url,
                '--project', project['project_id'],
                '--apikey', project['update_tokens'][0],
                self.clk_file.name
            ] + extra_arguments
        )

    def test_upload_with_verbose(self):
        project = self._create_project()
        # Upload
        runner = CliRunner()
        cli_result = runner.invoke(cli.cli,
                                   [
                                        'upload',
                                        '--verbose',
                                        '--server', self.url,
                                        '--project', project['project_id'],
                                        '--apikey', project['update_tokens'][0],
                                        self.clk_file.name

                                    ]
        )
        assert cli_result.exit_code == 0
        assert 'Uploading CLK data from {}'.format(self.clk_file.name) in cli_result.output
        assert 'Project ID: {}'.format(project['project_id']) in cli_result.output
        assert 'Uploading CLK data to the server' in cli_result.output

    def test_upload_to_entityservice(self):
        project = self._create_project()
        # Upload
        runner = CliRunner()
        cli_result = runner.invoke(cli.cli,
                                   [
                                        'upload',
                                        '--verbose',
                                        '--server', self.url,
                                        '--project', project['project_id'],
                                        '--apikey', project['update_tokens'][0],
                                        '--to_entityservice',
                                        self.clk_file.name

                                    ]
        )
        assert cli_result.exit_code == 0
        assert 'Uploading CLK data from {}'.format(self.clk_file.name) in cli_result.output
        assert 'Project ID: {}'.format(project['project_id']) in cli_result.output
        assert 'Uploading CLK data to the server' in cli_result.output

    def test_upload_with_blocks(self):
        project = self._create_project({'blocked': 'True'})
        # Upload
        runner = CliRunner()
        cli_result = runner.invoke(cli.cli,
                                   [
                                        'upload',
                                        '--verbose',
                                        '--server', self.url,
                                        '--project', project['project_id'],
                                        '--apikey', project['update_tokens'][0],
                                        '--blocks', self.block_file.name,
                                        self.clk_file.name

                                    ]
        )
        assert cli_result.exit_code == 0

    def test_upload_with_wrong_clks_blocks(self):
        project = self._create_project({'blocked': 'True'})
        # Upload
        runner = CliRunner()
        cli_result = runner.invoke(cli.cli,
                                   [
                                        'upload',
                                        '--verbose',
                                        '--server', self.url,
                                        '--project', project['project_id'],
                                        '--apikey', project['update_tokens'][0],
                                        '--blocks', self.block_file.name,
                                        self.clk_file_2.name

                                    ]
        )
        assert cli_result.exit_code == 1
        assert 'Size inconsistency: there are 50 CLKs but 100 encoding-to-blocks maps' == cli_result.exception.args[0]

    def test_upload_with_blocks_to_entityservice(self):
        project = self._create_project({'blocked': 'True'})
        # Upload
        runner = CliRunner()
        cli_result = runner.invoke(cli.cli,
                                   [
                                        'upload',
                                        '--verbose',
                                        '--server', self.url,
                                        '--project', project['project_id'],
                                        '--apikey', project['update_tokens'][0],
                                        '--blocks', self.block_file.name,
                                        '--to_entityservice',
                                        self.clk_file.name

                                    ]
        )
        assert cli_result.exit_code == 0

    def test_single_upload(self):
        self._test_single_upload([])

    def test_single_upload_retry_options(self):
        self._test_single_upload(self.retry_options_values)

    def test_2_party_upload_and_results(self):
        project, run = self._create_project_and_run()

        def get_coord_results():
            # Get results from coordinator
            return self.run_command_capture_output(
                [
                    'results',
                    '--server', self.url,
                    '--project', project['project_id'],
                    '--run', run['run_id'],
                    '--apikey', project['result_token']
                ]
            )

        # Upload Alice
        alice_upload = self.run_command_load_json_output(
            [
                'upload',
                '--server', self.url,
                '--project', project['project_id'],
                '--apikey', project['update_tokens'][0],
                self.clk_file.name
            ]
        )
        self.assertIn('receipt_token', alice_upload)

        out_early = get_coord_results()
        self.assertEqual("", out_early)

        # Upload Bob (subset of clks uploaded)
        bob_upload = self.run_command_load_json_output(
            [
                'upload',
                '--server', self.url,
                '--project', project['project_id'],
                '--apikey', project['update_tokens'][1],
                self.clk_file_2.name
            ]
        )

        self.assertIn('receipt_token', bob_upload)

        # Use the rest anonlinkclient to wait until the run is complete
        self.rest_client.wait_for_run(project['project_id'],
                                      run['run_id'],
                                      project['result_token'],
                                      timeout=ES_TIMEOUT)

        results_raw = get_coord_results()
        res = json.loads(results_raw)
        self.assertIn('mask', res)

        # Should be close to half ones. This is really just testing the service
        # not the command line tool.
        number_in_common = res['mask'].count(1)
        self.assertGreaterEqual(number_in_common / self.SAMPLES, 0.4)
        self.assertLessEqual(number_in_common / self.SAMPLES, 0.6)

        # Get results from first DP
        alice_res = self.run_command_load_json_output(
            [
                'results',
                '--server', self.url,
                '--project', project['project_id'],
                '--run', run['run_id'],
                '--apikey', alice_upload['receipt_token']
            ]
        )

        self.assertIn('permutation', alice_res)
        self.assertIn('rows', alice_res)

        # Get results from second DP
        bob_res = self.run_command_load_json_output(
            [
                'results',
                '--server', self.url,
                '--project', project['project_id'],
                '--run', run['run_id'],
                '--apikey', bob_upload['receipt_token']
            ]
        )

        self.assertIn('permutation', bob_res)
        self.assertIn('rows', bob_res)

    def test_multi_party_upload_and_results(self):
        project, run = self._create_project_and_run(
            {'type': 'groups', 'parties': '3'})

        def get_coord_results():
            # Get results from coordinator
            return self.run_command_capture_output(
                [
                    'results',
                    '--server', self.url,
                    '--project', project['project_id'],
                    '--run', run['run_id'],
                    '--apikey', project['result_token']
                ]
            )

        # Upload Alice
        alice_upload = self.run_command_load_json_output(
            [
                'upload',
                '--server', self.url,
                '--project', project['project_id'],
                '--apikey', project['update_tokens'][0],
                self.clk_file.name
            ]
        )
        self.assertIn('receipt_token', alice_upload)

        out_early = get_coord_results()
        self.assertEqual("", out_early)

        # Upload Bob (subset of clks uploaded)
        bob_upload = self.run_command_load_json_output(
            [
                'upload',
                '--server', self.url,
                '--project', project['project_id'],
                '--apikey', project['update_tokens'][1],
                self.clk_file_2.name
            ]
        )

        self.assertIn('receipt_token', bob_upload)

        out_early = get_coord_results()
        self.assertEqual("", out_early)

        # Upload Charlie (we're lazy and just reuse Bob)
        charlie_upload = self.run_command_load_json_output(
            [
                'upload',
                '--server', self.url,
                '--project', project['project_id'],
                '--apikey', project['update_tokens'][2],
                self.clk_file_2.name
            ]
        )

        self.assertIn('receipt_token', charlie_upload)

        # Use the rest anonlinkclient to wait until the run is complete
        self.rest_client.wait_for_run(project['project_id'],
                                      run['run_id'],
                                      project['result_token'],
                                      timeout=ES_TIMEOUT)
        results = get_coord_results()
        res = json.loads(results)
        self.assertIn('groups', res)

        # Recall that Bob and Charlie have the same samples. These form
        # half of Alice's samples.
        groups = res['groups']
        assert self.SAMPLES * .45 <= len(groups) <= self.SAMPLES * .55

        number_of_groups_of_three = sum(len(group) == 3 for group in groups)
        assert number_of_groups_of_three >= .9 * len(groups)
