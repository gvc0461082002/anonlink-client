import re
from typing import Sequence, Tuple
from blocklib import PPRLIndexPSignature


def compute_signatures(data: Sequence[Tuple[str, ...]], signature_config):
    """
    :param data: list of tuples E.g. ('0', 'Kenneth Bain', '1964/06/17', 'M')
    :param signature_config:
        A description of how the signatures should be generated.
        A simple type is "feature-value" which simply takes the feature
        mentioned at `feature-index`::

            {
                'type': 'feature-value',
                'feature-index': 3,
                'regex-pattern': ""
            }
    :return: A list of "signatures" per record in data.
    """
    algorithm = signature_config.get('type', 'not specified')

    if algorithm == 'not specified':
        raise ValueError("Compute signature type is not specified.")
    dic_signatures_record = {}
    for index in range(len(data)):
        if algorithm == 'feature-value':
            signatures = _compute_feature_value_signature(data[index], signature_config)
            for signature in signatures:
                if signature in dic_signatures_record:
                    dic_signatures_record[signature].append(index)
                else:
                    dic_signatures_record[signature] = [index]
        elif algorithm == 'p-sig':
            config = signature_config.get('config', 'not specified')
            if config == 'not specified':
                raise ValueError('Please provide config for P-Sig from blocklib')
            psig = PPRLIndexPSignature(config)
            # import IPython; IPython.embed()
            dic_signatures_record, bf= psig.build_invert_index(data)
        else:
            msg = 'The algorithm {} is not implemented yet'.format(algorithm)
            raise NotImplementedError(msg)

    return dic_signatures_record


def _compute_feature_value_signature(record, feature_value_config):
    """

    :param record: a tuple of values from the dataset
    :param feature_value_config: the configuration for a single signature algorithm
    :return: a list of signatures for this record.
    """
    index = feature_value_config.get('feature-index', 'not specified')
    # By default, keep the whole value if no regex-pattern is provided
    pattern = feature_value_config.get('regex-pattern', '.*')

    if index == 'not specified':
        raise ValueError("Signature index is not specified.")

    index = int(index)
    prog = re.compile(pattern)

    prog_output = prog.search(record[index])
    if prog_output:
        return [prog_output.group()]
    return []
