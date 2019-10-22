import clkhash
from poc.filter import filter_signatures
from poc.block_filter_generator import candidate_block_filter_from_signatures
from poc.server import compute_blocking_filter
from poc.signature_generator import compute_signatures


def compute_candidate_block_filter(data, blocking_config):
    """

    :param data:
    :param blocking_config:
    :return:
        A 3-tuple containing:
        - the candidate block filter (CBF) and
        - a dict mapping block index (e.g. index in the cbf) to the list of
          signatures that are associated with that cbf location, and
        - a dict mapping signatures to records
    """
    signature_config = blocking_config['signature']
    filter_config = blocking_config['filter']
    config = blocking_config['candidate-blocking-filter']

    candidate_signatures = compute_signatures(data, signature_config)
    signatures = filter_signatures(candidate_signatures, filter_config)
    return candidate_block_filter_from_signatures(signatures, config)


def create_reverse_index(block_filter, bf_map, sig_rec_map):
    """
    Two methods have been implemented that map to a list of records.

    - index based blocking: creates a block for every high bit in the
      bloom filter.
    - signature based blocking: creates a block for every individual
      signature.

    :param block_filter:
    :param bf_map:
    :param param:
    :return:
    """




def run_gender_blocking():

    blocking_config = {
        'signature': {
            # 'type': 'feature-value',
            'type': 'p-sig',
            'feature-index': 3,
            'config': {
                'num_hash_funct': 5,
                'bf_len': 2048,
                'attr_select_list': [3],
                'max_occur_ratio': 1.0,
                'min_occur_ratio': 0.001,
            }
        },
        'filter': {
            'type': 'none'
            # 'type': 'frequency',
            # 'min': 2,
            # 'max': 1000
        },
        'candidate-blocking-filter': {
            'type': 'dummy',
            'filter-length': 2,
            'values': ['F', 'M']
        }

    }

    data = list(clkhash.randomnames.NameList(100).names)
    print("Example PII", data[0])
    dp1_candidate_block_filter, cbf_map_1 = compute_candidate_block_filter(data[:75], blocking_config)
    dp2_candidate_block_filter, cbf_map_2 = compute_candidate_block_filter(data[50:], blocking_config)
    print("Candidate block filter dp1:", dp1_candidate_block_filter)
    print("Candidate block filter dp2:", dp2_candidate_block_filter)
    print("Candidate block filter map 1:", cbf_map_1)
    print("Candidate block filter map 2:", cbf_map_2)

    block_filter = compute_blocking_filter((dp1_candidate_block_filter, dp2_candidate_block_filter))
    print("Block filter:", block_filter)

    dp1_index = create_reverse_index(block_filter, cbf_map_1, 'todo GS? signature -> record mapping')



if __name__ == '__main__':
    run_gender_blocking()
