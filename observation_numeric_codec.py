"""Lossless storage shapes and IEEE-754 values; no analytical calculations."""
import base64
import struct
import copy


def compact_forecasts(report, full_sha256):
    """Do not duplicate raw/context-only evolution already in checkpoint traces.

    Every predeclared predictor (including censored ones), its exact evolution,
    forward results and joint patterns is kept. Omitted fields are inventoried;
    this is an explicit summary projection, not a claim of a full roundtrip.
    """
    result = copy.deepcopy(report)
    selected = [s for s in result['series'] if s.get('forecast_status') == 'evaluated']
    keys = {s['key'] for s in selected}
    if any(p['left'] not in keys or p['right'] not in keys for p in result['joint_patterns']):
        raise ValueError('numeric_evolution_compact_prediction_reference_missing')
    omitted = {}
    for s in result['series']:
        if s['key'] not in keys:
            omitted.setdefault(s['stage'], {}).setdefault(s['rule_id'], []).append(s['metric'])
    result['series'] = selected
    result['storage_profile'] = {
        'version':'forecast-complete-compact-v1', 'full_report_sha256':full_sha256,
        'original_series':len(report['series']), 'stored_predictor_series':len(selected),
        'omitted_context_series':omitted, 'rounding':False,
        'full_detail_source':'immutable_checkpoint_traces_and_local_laboratory',
    }
    return result


def factor_numbers(value):
    texts, shapes, numbers = [], [], []
    text_ids, shape_ids, number_ids = {}, {}, {}

    def encode(item):
        if isinstance(item, str):
            if item not in text_ids:
                text_ids[item] = len(texts); texts.append(item)
            return [-1, text_ids[item]]
        if isinstance(item, dict):
            keys = tuple(sorted(item))
            if keys not in shape_ids:
                shape_ids[keys] = len(shapes); shapes.append(list(keys))
            return [-2, shape_ids[keys], [encode(item[k]) for k in keys]]
        if isinstance(item, float):
            bits = struct.pack('<d', item)
            if bits not in number_ids:
                number_ids[bits] = len(numbers); numbers.append(bits)
            return [-3, number_ids[bits]]
        if isinstance(item, list):
            return [-4, [encode(v) for v in item]]
        return item

    root = encode(value)
    return {'texts': texts, 'shapes': shapes,
            'floats': base64.b64encode(b''.join(numbers)).decode('ascii'), 'root': root}


def expand_numbers(document):
    bits = base64.b64decode(document['floats'], validate=True)
    if len(bits) % 8:
        raise ValueError('numeric_codec_invalid_floats')
    numbers = [v[0] for v in struct.iter_unpack('<d', bits)]

    def indexed(values, index):
        if type(index) is not int or not 0 <= index < len(values):
            raise ValueError('numeric_codec_invalid_reference')
        return values[index]

    def decode(node):
        if not isinstance(node, list):
            return node
        if len(node) == 2 and node[0] == -1:
            return indexed(document['texts'], node[1])
        if len(node) == 2 and node[0] == -3:
            return indexed(numbers, node[1])
        if len(node) == 3 and node[0] == -2:
            keys = indexed(document['shapes'], node[1])
            if len(keys) != len(node[2]) or len(keys) != len(set(keys)):
                raise ValueError('numeric_codec_invalid_shape')
            return {k: decode(v) for k, v in zip(keys, node[2])}
        if len(node) == 2 and node[0] == -4:
            return [decode(v) for v in node[1]]
        raise ValueError('numeric_codec_invalid_node')

    return decode(document['root'])
