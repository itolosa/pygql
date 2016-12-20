from __future__ import absolute_import

import datetime

from graphql.language import ast
from graphql import GraphQLScalarType
import iso8601

def serialize(dt):
    assert isinstance(dt, (datetime.datetime, datetime.date)), (
        'Received not compatible datetime "{}"'.format(repr(dt))
    )
    return dt.isoformat()

def parse_literal(node):
    if isinstance(node, ast.StringValue):
        return parse_value(node.value)

def parse_value(value):
    return iso8601.parse_date(value)

DateTime = GraphQLScalarType('DateTime',
    serialize=serialize,
    parse_literal=parse_literal,
    parse_value=parse_value
)
