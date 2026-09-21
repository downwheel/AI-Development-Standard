"""Validate the deliberately small JSON-schema vocabulary exposed by this server."""
from __future__ import annotations
import re
from .common import fail

def validate(value, schema, path='input'):
    if 'anyOf' in schema:
        from .common import HarnessError
        for choice in schema['anyOf']:
            try:
                validate(value, choice, path)
                return
            except HarnessError:
                pass
        fail('invalid_input', path + ' does not match an allowed type.')
    expected = schema.get('type')
    types = expected if isinstance(expected, list) else [expected]
    kinds = {'object': lambda x:isinstance(x,dict), 'array':lambda x:isinstance(x,list), 'string':lambda x:isinstance(x,str),
             'integer':lambda x:type(x) is int, 'number':lambda x:type(x) in (int,float), 'boolean':lambda x:type(x) is bool, 'null':lambda x:x is None}
    if expected and not any(kinds[k](value) for k in types):
        fail('invalid_input', f'{path} must be {expected}.')
    if 'enum' in schema and value not in schema['enum']:
        fail('invalid_input', f'{path} has an unsupported value.')
    if 'const' in schema and value != schema['const']:
        fail('invalid_input', f'{path} differs from its required value.')
    if isinstance(value, dict):
        for key in schema.get('required', []):
            if key not in value:
                fail('invalid_input', f'{path}.{key} is required.')
        properties = schema.get('properties', {})
        for key, child in value.items():
            if key in properties:
                validate(child, properties[key], path + '.' + key)
            elif schema.get('additionalProperties') is False:
                fail('invalid_input', f'{path}.{key} is not supported.')
            elif isinstance(schema.get('additionalProperties'), dict):
                validate(child, schema['additionalProperties'], path + '.' + key)
    if isinstance(value, list):
        if not schema.get('minItems',0) <= len(value) <= schema.get('maxItems',10000):
            fail('invalid_input', path + ' has an invalid item count.')
        for i, child in enumerate(value):
            validate(child, schema.get('items',{}), f'{path}[{i}]')
    if isinstance(value, str):
        if not schema.get('minLength',0) <= len(value) <= schema.get('maxLength',2*1024*1024):
            fail('invalid_input', path + ' has an invalid length.')
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            fail('invalid_input', path + ' does not match its required format.')
    if type(value) in (int,float):
        if value < schema.get('minimum', float('-inf')) or value > schema.get('maximum',float('inf')):
            fail('invalid_input', path + ' is outside its allowed range.')

def obj(properties, required=()):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}

STR={'type':'string','minLength':1,'maxLength':4096}
BOOL={'type':'boolean'}
