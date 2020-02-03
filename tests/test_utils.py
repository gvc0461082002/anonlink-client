"""Test utils."""
import io
import json
import unittest
from bitarray import bitarray
from click.testing import CliRunner

from clkhash.serialization import serialize_bitarray
from anonlinkclient.utils import deserialize_filters, generate_candidate_blocks_from_csv, combine_clks_blocks
import anonlinkclient.cli as cli
from tests import *


class TestUtils(unittest.TestCase):

    def test_deserialize_bitarray(self):
        """Test deserialize bitarray."""
        # create simple bitarray bloom filter
        lst = [True, False, True, False] * 2
        bf = bitarray(lst)
        serialized_bf = serialize_bitarray(bf)
        deserialized_bf = deserialize_filters([serialized_bf])
        assert deserialized_bf == [bf]

    def test_generate_candidate_blocks_from_csv_exception(self):
        """Test exception case for generate candidate blocks from csv."""
        data = [[1, 'Joyce'],
                [2, 'Fred']]
        input_f = io.StringIO(str(data))
        schema_f = open(os.path.join(TESTDATA, 'bad-schema-v1.json'))

        # test invalid header
        header = 'Header'
        with self.assertRaises(ValueError):
            generate_candidate_blocks_from_csv(input_f, schema_f, header)

    def test_combine_clks_blocks(self):
        """Test combine clks and blocks."""
        _, fname_clks = tempfile.mkstemp(suffix='.json', text=True)
        _, fname_blks = tempfile.mkstemp(suffix='.json', text=True)

        runner = CliRunner()

        # use dirty data as example
        blocking_schema_path = os.path.join(TESTDATA, 'dirty-data-blocking-schema.json')
        linking_schema_path = os.path.join(TESTDATA, 'dirty-data-schema.json')
        data_path = os.path.join(TESTDATA, 'dirty_1000_50_1.csv')

        # block dirty data locally and save to temporary file fname_blks
        with open(fname_blks, 'wt') as output:
            runner.invoke(
                cli.cli,
                ['block', data_path, blocking_schema_path, output.name])

        # encode dirty data locally and save to temporary file fname_blks
        with open(fname_clks, 'wt') as output:
            runner.invoke(
                cli.cli,
                ['hash', data_path, 'horse', linking_schema_path, output.name]
            )

        # test exception
        with self.assertRaises(ValueError):
            combine_clks_blocks(open(data_path, 'r'), open(data_path, 'r'))

        # test normal case
        cmb = combine_clks_blocks(open(fname_clks, 'r'), open(fname_blks, 'r'))
        with open(fname_clks, 'r') as f:
            clks = json.load(f)['clks']
        assert len(cmb) == len(clks)


