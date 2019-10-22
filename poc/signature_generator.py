import re


def compute_signatures(data, signature_config):
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
    signatures = []
    for dtuple in data:
        if algorithm == 'feature-value':
            signatures.append(_compute_feature_value_signature(dtuple, signature_config))
        return signatures
    else:
        msg = 'The algorithm {} is not implemented yet'.format(algorithm)
        raise NotImplementedError(msg)


def _compute_feature_value_signature(record, feature_value_config):
    """

    :param record: a tuple of values from the dataset
    :param feature_value_config: the configuration for a single signature algorithm
    :return: a list of signatures for this record.
    """
    index = feature_value_config.get('feature-index', 'not specified')
    # By default, keep the whole value if no regex-pattern is provided
    pattern = feature_value_config.get('pattern', '.*')

    if index == 'not specified':
        raise ValueError("Signature index is not specified.")

    index = int(index)
    prog = re.compile(pattern)
    list_signatures = prog.match(record[index])
    return list_signatures
